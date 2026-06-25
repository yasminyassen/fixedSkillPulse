import logging

from ai_services.requirements.coverage.pipeline import backfill_developer_task_results
from ai_services.requirements.coverage.retrieval import retrieve_code_for_developer_task
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.api.auth import get_current_user
from app.db.database import SessionLocal, get_db
from app.db.models import (
    AcCoverageResult,
    AcCoverageStatus,
    CoverageRunStatus,
    RequirementCoverageRun,
    RequirementDocument,
    StoryCoverageSummary,
    TechnicalTask,
    User,
    UserStory,
)
from app.schemas.coverage_schemas import CoverageRunResponse, CoverageRunSummaryResponse
from app.services.requirement_coverage_service import (
    build_requirement_snapshots,
    coverage_stale_state,
    ensure_repository_ready_for_requirements,
    execute_coverage_run,
    get_latest_confirmed_document,
    get_latest_coverage_run,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/requirements/coverage", tags=["Requirement Coverage"])


def _run_coverage_background(coverage_run_id: int, manager_user_id: int):
    db = SessionLocal()
    try:
        import asyncio

        asyncio.run(
            execute_coverage_run(
                db,
                coverage_run_id=coverage_run_id,
                manager_user_id=manager_user_id,
            )
        )
    except Exception as exc:
        logger.exception("Background coverage detection failed: %s", exc)
    finally:
        db.close()


def _backfill_developer_task_coverage_background(coverage_run_id: int):
    db = SessionLocal()
    try:
        import asyncio

        asyncio.run(backfill_developer_task_results(db, coverage_run_id=coverage_run_id))
    except Exception as exc:
        logger.exception("Background developer task coverage backfill failed: %s", exc)
    finally:
        db.close()


def _value(value):
    return getattr(value, "value", value)


def _ac_text(story: UserStory, ac_id: int) -> str:
    for ac in story.acceptance_criteria or []:
        if isinstance(ac, dict) and ac.get("id") == ac_id:
            return ac.get("text") or ""
    return ""


def _coverage_pct(score: float | None) -> float:
    return round(float(score or 0.0) * 100, 2)


def _summary_counts(story_summaries: list[StoryCoverageSummary]) -> dict:
    counts = {
        "implemented_stories": 0,
        "partially_implemented_stories": 0,
        "missing_stories": 0,
    }
    for summary in story_summaries:
        status = _value(summary.status)
        if status == "implemented":
            counts["implemented_stories"] += 1
        elif status == "partially_implemented":
            counts["partially_implemented_stories"] += 1
        else:
            counts["missing_stories"] += 1
    return counts


def _run_block(db: Session, run: RequirementCoverageRun) -> dict:
    stale = coverage_stale_state(db, run) if run.status == CoverageRunStatus.completed else {
        "is_stale": False,
        "implementation_stale": False,
        "ownership_stale": False,
        "stale_reasons": [],
    }
    return {
        "id": run.id,
        "repository_id": run.repository_id,
        "document_id": run.document_id,
        "analysis_run_id": run.analysis_run_id,
        "status": _value(run.status),
        "overall_coverage": run.overall_coverage,
        "overall_coverage_percent": _coverage_pct(run.overall_coverage),
        "branch": run.branch,
        "commit_sha": run.commit_sha,
        "created_at": run.created_at,
        "completed_at": run.completed_at,
        "error_message": run.error_message,
        **stale,
    }


def _task_payload(task: TechnicalTask, users_by_id: dict[int, User]) -> dict:
    assignee = users_by_id.get(task.assigned_to) if task.assigned_to else None
    return {
        "task_id": task.id,
        "story_id": task.story_id,
        "description": task.description,
        "type": _value(task.type),
        "status": _value(task.status),
        "assigned_to": task.assigned_to,
        "assigned_name": assignee.full_name if assignee else None,
        "assigned_username": assignee.username if assignee else None,
        "assigned_specialization": _value(assignee.specialization) if assignee else None,
        "ac_ids": task.ac_ids or [],
        "due_date": task.due_date,
    }


def _evidence_payload(items: list | None, used_in_scoring: bool = True) -> list[dict]:
    output = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        output.append({
            "file_path": item.get("file_path"),
            "symbol_name": item.get("symbol_name"),
            "symbol_type": item.get("symbol_type"),
            "start_line": item.get("start_line"),
            "end_line": item.get("end_line"),
            "chunk_id": item.get("chunk_id"),
            "retrieval_source": item.get("retrieval_source") or "primary",
            "similarity": item.get("similarity", item.get("score")),
            "used_in_scoring": used_in_scoring,
            "excerpt": item.get("excerpt"),
        })
    return output


def _developer_task_evidence(run: RequirementCoverageRun, story: UserStory, task: TechnicalTask) -> list[dict]:
    stored = _developer_task_result(run, task.id)
    if stored is not None:
        return _evidence_payload(stored.get("evidence"), used_in_scoring=True)

    linked_ac_texts = [
        _ac_text(story, ac_id)
        for ac_id in (task.ac_ids or [])
    ]
    linked_ac_texts = [text for text in linked_ac_texts if text]
    try:
        hits = retrieve_code_for_developer_task(
            run.id,
            task.description,
            linked_ac_texts=linked_ac_texts,
            top_k=8,
        )
    except Exception as exc:
        logger.warning(
            "Developer task evidence retrieval failed: run=%s task=%s error=%s",
            run.id,
            task.id,
            exc,
        )
        return []
    return _evidence_payload(
        [
            {
                **hit,
                "similarity": hit.get("score"),
                "excerpt": (hit.get("chunk_text") or "")[:500],
            }
            for hit in hits
        ],
        used_in_scoring=False,
    )


def _developer_task_result(run: RequirementCoverageRun, task_id: int) -> dict | None:
    for result in run.developer_task_results or []:
        if isinstance(result, dict) and result.get("task_id") == task_id:
            return result
    return None


def _build_manager_dashboard(db: Session, run: RequirementCoverageRun) -> dict:
    stories = (
        db.query(UserStory)
        .options(joinedload(UserStory.technical_tasks))
        .filter(UserStory.document_id == run.document_id)
        .order_by(UserStory.id.asc())
        .all()
    )
    story_by_id = {story.id: story for story in stories}
    summaries = {s.story_id: s for s in run.story_summaries}
    ac_results_by_story: dict[int, list[AcCoverageResult]] = {}
    for ac_result in run.ac_results:
        ac_results_by_story.setdefault(ac_result.story_id, []).append(ac_result)

    user_ids = {
        task.assigned_to
        for story in stories
        for task in story.technical_tasks
        if task.assigned_to
    }
    users_by_id = {
        user.id: user
        for user in db.query(User).filter(User.id.in_(user_ids)).all()
    } if user_ids else {}

    story_payloads = []
    for story in stories:
        summary = summaries.get(story.id)
        tasks = [_task_payload(task, users_by_id) for task in story.technical_tasks]
        assigned_developers = []
        seen_assignees = set()
        for task in story.technical_tasks:
            assignee = users_by_id.get(task.assigned_to) if task.assigned_to else None
            if assignee and assignee.id not in seen_assignees:
                seen_assignees.add(assignee.id)
                assigned_developers.append({
                    "id": assignee.id,
                    "name": assignee.full_name,
                    "username": assignee.username,
                    "specialization": _value(assignee.specialization),
                })

        ac_payloads = []
        for result in sorted(ac_results_by_story.get(story.id, []), key=lambda r: r.ac_id):
            linked_task_ids = [
                task.id
                for task in story.technical_tasks
                if result.ac_id in (task.ac_ids or [])
            ]
            ac_payloads.append({
                "result_id": result.id,
                "ac_id": result.ac_id,
                "text": _ac_text(story, result.ac_id),
                "status": _value(result.status),
                "score": result.score,
                "confidence": result.confidence,
                "linked_task_ids": linked_task_ids,
                "task_id": result.task_id,
                "matched_chunk_ids": result.matched_chunk_ids or [],
                "llm_reason": result.llm_reason,
                "evidence": _evidence_payload(result.evidence),
            })

        story_payloads.append({
            "story_id": story.id,
            "document_id": story.document_id,
            "story_code": story.story_code,
            "title": story.title,
            "description": story.description,
            "role": story.role,
            "feature": story.feature,
            "benefit": story.benefit,
            "priority": story.priority,
            "tags": story.tags or [],
            "coverage_score": summary.coverage_score if summary else None,
            "coverage_percent": _coverage_pct(summary.coverage_score) if summary else None,
            "status": _value(summary.status) if summary else None,
            "evaluated": summary is not None,
            "last_coverage_run_id": run.id if summary else None,
            "matched_symbols": summary.matched_symbols if summary else [],
            "assigned_developers": assigned_developers,
            "tasks": tasks,
            "acceptance_criteria": ac_payloads,
        })

    summary_counts = _summary_counts(list(summaries.values()))
    trends = [
        {
            "run_id": row.id,
            "completed_at": row.completed_at,
            "overall_coverage": row.overall_coverage,
            "overall_coverage_percent": _coverage_pct(row.overall_coverage),
        }
        for row in (
            db.query(RequirementCoverageRun)
            .filter(
                RequirementCoverageRun.repository_id == run.repository_id,
                RequirementCoverageRun.status == CoverageRunStatus.completed,
            )
            .order_by(RequirementCoverageRun.completed_at.asc())
            .limit(20)
            .all()
        )
    ]

    total_acs = sum(len(story.acceptance_criteria or []) for story in stories)
    return {
        "run": _run_block(db, run),
        "active_run": None,
        "is_analysis_running": False,
        "summary": {
            **summary_counts,
            "total_stories": len(summaries),
            "total_acceptance_criteria": len(run.ac_results),
            "confirmed_stories": len(stories),
            "confirmed_acceptance_criteria": total_acs,
        },
        "stories": story_payloads,
        "trends": trends,
        "discovery_links": run.discovery_links or [],
    }


def _empty_manager_dashboard() -> dict:
    return {
        "run": None,
        "active_run": None,
        "is_analysis_running": False,
        "summary": None,
        "stories": [],
        "trends": [],
        "discovery_links": [],
    }


def _latest_active_coverage_run(db: Session, repo_id: int) -> RequirementCoverageRun | None:
    return (
        db.query(RequirementCoverageRun)
        .filter(
            RequirementCoverageRun.repository_id == repo_id,
            RequirementCoverageRun.status.in_([CoverageRunStatus.pending, CoverageRunStatus.running]),
        )
        .order_by(RequirementCoverageRun.created_at.desc())
        .first()
    )


def _latest_completed_coverage_run(db: Session, repo_id: int) -> RequirementCoverageRun | None:
    return (
        db.query(RequirementCoverageRun)
        .options(
            joinedload(RequirementCoverageRun.story_summaries),
            joinedload(RequirementCoverageRun.ac_results),
        )
        .filter(
            RequirementCoverageRun.repository_id == repo_id,
            RequirementCoverageRun.status == CoverageRunStatus.completed,
        )
        .order_by(RequirementCoverageRun.completed_at.desc(), RequirementCoverageRun.created_at.desc())
        .first()
    )


def _attach_active_run_state(db: Session, payload: dict, active_run: RequirementCoverageRun | None) -> dict:
    payload["active_run"] = _run_block(db, active_run) if active_run else None
    payload["is_analysis_running"] = active_run is not None
    return payload


def _build_developer_dashboard(db: Session, run: RequirementCoverageRun, current_user: User) -> dict | None:
    assigned_tasks = (
        db.query(TechnicalTask)
        .join(UserStory, TechnicalTask.story_id == UserStory.id)
        .filter(
            UserStory.document_id == run.document_id,
            TechnicalTask.assigned_to == current_user.id,
        )
        .order_by(TechnicalTask.id.asc())
        .all()
    )
    if not assigned_tasks:
        return None

    assigned_story_ids = sorted({task.story_id for task in assigned_tasks})
    stories = (
        db.query(UserStory)
        .filter(UserStory.id.in_(assigned_story_ids))
        .order_by(UserStory.id.asc())
        .all()
    )
    tasks_by_story: dict[int, list[TechnicalTask]] = {}
    visible_ac_ids_by_story: dict[int, set[int]] = {}
    for task in assigned_tasks:
        tasks_by_story.setdefault(task.story_id, []).append(task)
        visible_ac_ids_by_story.setdefault(task.story_id, set()).update(task.ac_ids or [])

    ac_results_by_story: dict[int, list[AcCoverageResult]] = {}
    for result in run.ac_results:
        if result.story_id in visible_ac_ids_by_story and result.ac_id in visible_ac_ids_by_story[result.story_id]:
            ac_results_by_story.setdefault(result.story_id, []).append(result)

    summary = {
        "assigned_stories": len(assigned_story_ids),
        "assigned_tasks": len(assigned_tasks),
        "covered_criteria": 0,
        "partial_criteria": 0,
        "missing_criteria": 0,
        "has_developer_task_results": bool(run.developer_task_results),
    }
    story_payloads = []
    for story in stories:
        visible_results = sorted(ac_results_by_story.get(story.id, []), key=lambda r: r.ac_id)
        ac_payloads = []
        for result in visible_results:
            status = _value(result.status)
            if status == AcCoverageStatus.covered.value:
                summary["covered_criteria"] += 1
            elif status == AcCoverageStatus.partially_covered.value:
                summary["partial_criteria"] += 1
            else:
                summary["missing_criteria"] += 1
            ac_payloads.append({
                "result_id": result.id,
                "ac_id": result.ac_id,
                "text": _ac_text(story, result.ac_id),
                "status": status,
                "score": result.score,
                "confidence": result.confidence,
                "linked_task_ids": [
                    task.id
                    for task in tasks_by_story.get(story.id, [])
                    if result.ac_id in (task.ac_ids or [])
                ],
                "matched_chunk_ids": result.matched_chunk_ids or [],
                "llm_reason": result.llm_reason,
                "evidence": _evidence_payload(result.evidence),
            })

        visible_score = (
            sum(result.score for result in visible_results) / len(visible_results)
            if visible_results
            else 0.0
        )
        story_payloads.append({
            "story_id": story.id,
            "story_code": story.story_code,
            "title": story.title,
            "description": story.description,
            "priority": story.priority,
            "visible_coverage_score": round(visible_score, 4),
            "visible_coverage_percent": _coverage_pct(visible_score),
            "tasks": [
                _developer_task_payload(run, story, task)
                for task in tasks_by_story.get(story.id, [])
            ],
            "acceptance_criteria": ac_payloads,
        })

    return {
        "run": {
            key: value
            for key, value in _run_block(db, run).items()
            if key not in {"overall_coverage", "overall_coverage_percent"}
        },
        "has_coverage_run": True,
        "has_developer_task_results": bool(run.developer_task_results),
        "developer": {
            "id": current_user.id,
            "name": current_user.full_name,
            "username": current_user.username,
            "specialization": _value(current_user.specialization),
        },
        "summary": summary,
        "stories": story_payloads,
    }


def _developer_task_payload(run: RequirementCoverageRun, story: UserStory, task: TechnicalTask) -> dict:
    task_result = _developer_task_result(run, task.id)
    return {
        "task_id": task.id,
        "story_id": task.story_id,
        "description": task.description,
        "type": _value(task.type),
        "status": _value(task.status),
        "ac_ids": task.ac_ids or [],
        "due_date": task.due_date,
        "has_linked_acceptance_criteria": bool(task.ac_ids),
        "task_coverage": {
            "status": task_result.get("status") if task_result else None,
            "score": task_result.get("score") if task_result else None,
            "confidence": task_result.get("confidence") if task_result else None,
            "reason": task_result.get("reason") if task_result else None,
            "matched_chunk_ids": task_result.get("matched_chunk_ids") if task_result else [],
        } if task_result else None,
        "task_evidence": _developer_task_evidence(run, story, task),
    }


@router.post("/repositories/{repo_id}/detect", response_model=CoverageRunSummaryResponse)
async def detect_coverage(
    repo_id: int,
    background_tasks: BackgroundTasks,
    document_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role.value != "manager":
        raise HTTPException(status_code=403, detail="Only managers can run coverage detection.")
    try:
        latest_analysis = ensure_repository_ready_for_requirements(db, repo_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if document_id is None:
        doc = get_latest_confirmed_document(db, repo_id)
        if not doc:
            raise HTTPException(status_code=400, detail="No confirmed PRD for this repository.")
        document_id = doc.id

    snapshots = build_requirement_snapshots(db, document_id)
    pending = RequirementCoverageRun(
        repository_id=repo_id,
        document_id=document_id,
        analysis_run_id=latest_analysis.id,
        branch=latest_analysis.branch,
        commit_sha=latest_analysis.commit_sha,
        requirements_snapshot_hash=snapshots["requirements_snapshot_hash"],
        tasks_snapshot_hash=snapshots["tasks_snapshot_hash"],
        assignments_snapshot_hash=snapshots["assignments_snapshot_hash"],
        status=CoverageRunStatus.pending,
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)

    background_tasks.add_task(_run_coverage_background, pending.id, current_user.id)

    return pending


@router.get("/repositories/{repo_id}")
def get_repository_coverage(
    repo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    active_run = _latest_active_coverage_run(db, repo_id)
    completed_run = _latest_completed_coverage_run(db, repo_id)
    if not completed_run and not active_run:
        return None
    if not completed_run:
        return _attach_active_run_state(db, _empty_manager_dashboard(), active_run)
    return _attach_active_run_state(db, _build_manager_dashboard(db, completed_run), active_run)


@router.get("/repositories/{repo_id}/runs")
def get_repository_coverage_runs(
    repo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role.value != "manager":
        raise HTTPException(status_code=403, detail="Only managers can view repository coverage runs.")
    rows = (
        db.query(RequirementCoverageRun)
        .filter(RequirementCoverageRun.repository_id == repo_id)
        .order_by(RequirementCoverageRun.created_at.desc())
        .all()
    )
    return [_run_block(db, row) for row in rows]


@router.post("/repositories/{repo_id}/refresh-ownership")
def refresh_repository_coverage_ownership(
    repo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role.value != "manager":
        raise HTTPException(status_code=403, detail="Only managers can refresh coverage ownership.")

    run = get_latest_coverage_run(db, repo_id)
    if not run or run.status != CoverageRunStatus.completed:
        raise HTTPException(status_code=404, detail="No completed coverage run exists for this repository.")

    snapshots = build_requirement_snapshots(db, run.document_id)
    run.assignments_snapshot_hash = snapshots["assignments_snapshot_hash"]
    db.commit()
    db.refresh(run)
    return _build_manager_dashboard(db, run)


@router.get("/runs/{run_id}", response_model=CoverageRunResponse)
def get_coverage_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = (
        db.query(RequirementCoverageRun)
        .options(
            joinedload(RequirementCoverageRun.story_summaries),
            joinedload(RequirementCoverageRun.ac_results),
        )
        .filter(RequirementCoverageRun.id == run_id)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Coverage run not found")
    return run


@router.get("/repositories/{repo_id}/developer")
def get_developer_coverage(
    repo_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Developer view: coverage filtered to assigned tasks and linked acceptance criteria."""
    run = _latest_completed_coverage_run(db, repo_id)
    if not run:
        return None
    if not run.developer_task_results:
        background_tasks.add_task(_backfill_developer_task_coverage_background, run.id)
    return _build_developer_dashboard(db, run, current_user)
