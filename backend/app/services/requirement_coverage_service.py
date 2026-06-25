"""Orchestrates repo checkout + coverage pipeline execution."""

from __future__ import annotations

import logging
import hashlib
import json

from sqlalchemy.orm import Session

from ai_services.requirements.coverage.pipeline import run_coverage_pipeline
from app.core.auth_utils import decrypt_github_token
from app.db.models import (
    AnalysisRun,
    CoverageRunStatus,
    DocumentStatus,
    RequirementCoverageRun,
    RequirementDocument,
    Repository,
    User,
    UserStory,
    TechnicalTask,
)
from app.services.analysis_orchestrator import _prepare_repo_checkout, resolve_github_identity
from app.services.github_client import read_local_source_files

logger = logging.getLogger(__name__)


def get_latest_confirmed_document(db: Session, repository_id: int) -> RequirementDocument | None:
    return (
        db.query(RequirementDocument)
        .filter(
            RequirementDocument.repository_id == repository_id,
            RequirementDocument.status == DocumentStatus.confirmed,
        )
        .order_by(RequirementDocument.processed_at.desc())
        .first()
    )


def get_latest_coverage_run(db: Session, repository_id: int) -> RequirementCoverageRun | None:
    return (
        db.query(RequirementCoverageRun)
        .filter(RequirementCoverageRun.repository_id == repository_id)
        .order_by(RequirementCoverageRun.created_at.desc())
        .first()
    )


def get_latest_successful_analysis(db: Session, repository_id: int) -> AnalysisRun | None:
    return (
        db.query(AnalysisRun)
        .filter(
            AnalysisRun.repository_id == repository_id,
            AnalysisRun.analysis_scope == "repository",
            AnalysisRun.status == "completed",
        )
        .order_by(AnalysisRun.completed_at.desc(), AnalysisRun.triggered_at.desc())
        .first()
    )


def ensure_repository_ready_for_requirements(db: Session, repository_id: int) -> AnalysisRun:
    latest = (
        db.query(AnalysisRun)
        .filter(
            AnalysisRun.repository_id == repository_id,
            AnalysisRun.analysis_scope == "repository",
        )
        .order_by(AnalysisRun.triggered_at.desc())
        .first()
    )
    if not latest:
        raise ValueError("Repository analysis must complete before requirements can be confirmed.")
    if latest.status != "completed":
        raise ValueError("Latest repository analysis is not completed. Resolve analysis issues before continuing.")
    return latest


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_requirement_snapshots(db: Session, document_id: int) -> dict[str, str]:
    stories = (
        db.query(UserStory)
        .filter(UserStory.document_id == document_id)
        .order_by(UserStory.id.asc())
        .all()
    )
    story_payload = [
        {
            "id": s.id,
            "title": s.title,
            "description": s.description,
            "role": s.role,
            "feature": s.feature,
            "benefit": s.benefit,
            "acceptance_criteria": s.acceptance_criteria,
            "priority": s.priority,
            "tags": s.tags,
        }
        for s in stories
    ]
    tasks = (
        db.query(TechnicalTask)
        .join(UserStory, TechnicalTask.story_id == UserStory.id)
        .filter(UserStory.document_id == document_id)
        .order_by(TechnicalTask.id.asc())
        .all()
    )
    task_payload = [
        {
            "id": t.id,
            "story_id": t.story_id,
            "description": t.description,
            "type": getattr(t.type, "value", t.type),
            "ac_ids": t.ac_ids,
        }
        for t in tasks
    ]
    assignment_payload = [
        {
            "id": t.id,
            "assigned_to": t.assigned_to,
            "status": getattr(t.status, "value", t.status),
            "due_date": t.due_date,
        }
        for t in tasks
    ]
    return {
        "requirements_snapshot_hash": _stable_hash(story_payload),
        "tasks_snapshot_hash": _stable_hash(task_payload),
        "assignments_snapshot_hash": _stable_hash(assignment_payload),
    }


def coverage_stale_state(db: Session, run: RequirementCoverageRun) -> dict:
    snapshots = build_requirement_snapshots(db, run.document_id)
    reasons: list[str] = []
    implementation_reasons: list[str] = []
    ownership_reasons: list[str] = []

    if run.requirements_snapshot_hash and run.requirements_snapshot_hash != snapshots["requirements_snapshot_hash"]:
        implementation_reasons.append("requirements_changed")
    if run.tasks_snapshot_hash and run.tasks_snapshot_hash != snapshots["tasks_snapshot_hash"]:
        implementation_reasons.append("technical_tasks_changed")
    if run.assignments_snapshot_hash and run.assignments_snapshot_hash != snapshots["assignments_snapshot_hash"]:
        ownership_reasons.append("assignments_changed")

    latest_analysis = get_latest_successful_analysis(db, run.repository_id)
    if latest_analysis:
        if run.analysis_run_id and latest_analysis.id != run.analysis_run_id:
            implementation_reasons.append("new_analysis_run_available")
        if run.branch and latest_analysis.branch and run.branch != latest_analysis.branch:
            implementation_reasons.append("repository_branch_changed")
        if run.commit_sha and latest_analysis.commit_sha and run.commit_sha != latest_analysis.commit_sha:
            implementation_reasons.append("repository_commit_changed")

    reasons.extend(implementation_reasons)
    reasons.extend(ownership_reasons)
    return {
        "is_stale": bool(reasons),
        "implementation_stale": bool(implementation_reasons),
        "ownership_stale": bool(ownership_reasons),
        "stale_reasons": reasons,
    }


async def execute_coverage_run(
    db: Session,
    *,
    coverage_run_id: int,
    manager_user_id: int,
) -> RequirementCoverageRun:
    run = db.query(RequirementCoverageRun).filter(RequirementCoverageRun.id == coverage_run_id).first()
    if not run:
        raise ValueError("Coverage run not found")

    document = db.query(RequirementDocument).filter(RequirementDocument.id == run.document_id).first()
    if not document or document.status != DocumentStatus.confirmed:
        run.status = CoverageRunStatus.failed
        run.error_message = "Requirement document must be confirmed before coverage detection"
        db.commit()
        raise ValueError(run.error_message)

    repo = db.query(Repository).filter(Repository.id == run.repository_id).first()
    if not repo:
        run.status = CoverageRunStatus.failed
        run.error_message = "Repository not found"
        db.commit()
        raise ValueError(run.error_message)

    manager = db.query(User).filter(User.id == manager_user_id).first()
    token = None
    if manager and repo.is_private:
        gh_token, _ = await resolve_github_identity(db, manager)
        token = gh_token
    elif manager and manager.github_access_token:
        token = decrypt_github_token(manager.github_access_token)

    latest_analysis = (
        get_latest_successful_analysis(db, run.repository_id)
    )
    if not latest_analysis:
        run.status = CoverageRunStatus.failed
        run.error_message = "Repository analysis must complete successfully before coverage detection"
        db.commit()
        raise ValueError(run.error_message)
    run.analysis_run_id = latest_analysis.id
    run.branch = latest_analysis.branch
    run.commit_sha = latest_analysis.commit_sha
    snapshots = build_requirement_snapshots(db, run.document_id)
    run.requirements_snapshot_hash = snapshots["requirements_snapshot_hash"]
    run.tasks_snapshot_hash = snapshots["tasks_snapshot_hash"]
    run.assignments_snapshot_hash = snapshots["assignments_snapshot_hash"]
    db.commit()
    branch = latest_analysis.branch if latest_analysis and latest_analysis.branch else "main"

    temp_dir = None
    try:
        clone_path, temp_dir = _prepare_repo_checkout(
            repo_url=repo.url,
            branch=branch,
            token=token or "",
            is_private=bool(repo.is_private),
            repo_name=repo.name,
            full_name=repo.full_name,
        )
        source_files = read_local_source_files(clone_path)
        await run_coverage_pipeline(
            db,
            coverage_run_id=run.id,
            repo_path=clone_path,
            source_files=source_files,
        )
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()

    db.refresh(run)
    return run
