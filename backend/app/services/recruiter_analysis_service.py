import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import AnalysisRun, RecruiterCandidate, Repository, RepositoryAnalysis, SkillScore, User
from app.services.analysis_orchestrator import background_analysis_task
from app.services.github_client import get_branch_head_sha, verify_repo_access
from app.services.sonarqube_score_service import build_skill_score_fields, build_sonar_repo_summary

logger = logging.getLogger(__name__)


async def schedule_recruiter_repo_analysis(
    *,
    db: Session,
    background_tasks: BackgroundTasks,
    current_user: User,
    token: str,
    candidate_name: str,
    repo_url: str,
    full_name: str,
    repo_name: str,
    branch: str,
    force_reanalyze: bool,
    task_id: int | None = None,
) -> dict[str, Any]:
    analysis_version = settings.analysis_version
    github_avatar_url: str | None = None
    github_login: str | None = None

    try:
        repo_data = await verify_repo_access(token, full_name)
    except Exception:
        return {
            "scheduled": False,
            "candidate": candidate_name,
            "github_avatar_url": github_avatar_url,
            "repo_name": repo_name,
            "html_url": repo_url,
            "default_branch": branch,
            "reason": "github_repo_lookup_failed",
        }

    if repo_data.get("private"):
        return {
            "scheduled": False,
            "candidate": candidate_name,
            "github_avatar_url": github_avatar_url,
            "repo_name": repo_name,
            "html_url": repo_url,
            "default_branch": branch,
            "reason": "private_repository_not_supported",
        }

    default_branch = repo_data.get("default_branch") or branch or "main"
    owner = repo_data.get("owner") or {}
    github_avatar_url = owner.get("avatar_url")
    github_login = owner.get("login")
    head_sha = await get_branch_head_sha(token, full_name, default_branch)
    if not head_sha:
        return {
            "scheduled": False,
            "candidate": candidate_name,
            "github_avatar_url": github_avatar_url,
            "repo_name": repo_name,
            "html_url": repo_url,
            "default_branch": default_branch,
            "reason": "branch_not_found",
        }

    html_url = repo_data.get("html_url") or repo_url
    db_repo = db.query(Repository).filter(Repository.github_repo_id == str(repo_data.get("id"))).first()
    if not db_repo:
        db_repo = Repository(
            name=repo_name,
            full_name=full_name,
            url=html_url,
            github_repo_id=str(repo_data.get("id")),
            is_private=bool(repo_data.get("private")),
        )
        db.add(db_repo)
        db.commit()
        db.refresh(db_repo)

    existing_analysis = (
        db.query(RepositoryAnalysis)
        .filter(
            RepositoryAnalysis.repository_id == db_repo.id,
            RepositoryAnalysis.user_id == current_user.id,
        )
        .order_by(RepositoryAnalysis.id.desc())
        .first()
    )

    last_run_exists = False
    if existing_analysis and existing_analysis.last_run_id:
        last_run_exists = (
            db.query(AnalysisRun)
            .filter(AnalysisRun.id == existing_analysis.last_run_id)
            .first()
        ) is not None

    needs_reanalysis = (
        force_reanalyze
        or not existing_analysis
        or not last_run_exists
        or existing_analysis.latest_commit_sha != head_sha
        or existing_analysis.analysis_version != analysis_version
        or existing_analysis.analysis_status == "failed"
    )

    if not needs_reanalysis and existing_analysis:
        sonar_summary: dict[str, Any] = {}
        skill_fields: dict[str, Any] = {"skill_score": None, "skill_score_level": "Unavailable"}
        if existing_analysis.last_run_id:
            existing_run = db.query(AnalysisRun).filter(AnalysisRun.id == existing_analysis.last_run_id).first()
            if existing_run:
                existing_candidate = (
                    db.query(RecruiterCandidate)
                    .filter(RecruiterCandidate.analysis_run_id == existing_run.id)
                    .first()
                )
                if existing_candidate and task_id and existing_candidate.task_id is None:
                    existing_candidate.task_id = task_id
                if existing_candidate and github_login and not existing_candidate.github_login:
                    existing_candidate.github_login = github_login
                if existing_candidate and github_avatar_url and not existing_candidate.github_avatar_url:
                    existing_candidate.github_avatar_url = github_avatar_url
                if existing_candidate:
                    db.commit()
                sonar_summary = build_sonar_repo_summary(existing_run)
                score_row = (
                    db.query(SkillScore)
                    .filter(
                        SkillScore.analysis_run_id == existing_run.id,
                        SkillScore.user_id == current_user.id,
                    )
                    .first()
                )
                skill_fields = build_skill_score_fields(
                    score_row,
                    sonar_health_score=sonar_summary.get("sonar_health_score"),
                    security_score=getattr(score_row, "security_awareness_score", None),
                )

        return {
            "scheduled": False,
            "candidate": candidate_name,
            "github_avatar_url": github_avatar_url,
            "repo_name": repo_name,
            "clone_path": "",
            "html_url": html_url,
            "default_branch": default_branch,
            "analysis_run_id": existing_analysis.last_run_id,
            "analysis_status": existing_analysis.analysis_status,
            "status": "skipped_no_changes" if existing_analysis.analysis_status == "completed" else existing_analysis.analysis_status,
            "latest_commit_sha": existing_analysis.latest_commit_sha,
            "analyzed_at": existing_analysis.analyzed_at,
            "analysis_version": existing_analysis.analysis_version,
            **skill_fields,
            "sonar_health_score": sonar_summary.get("sonar_health_score"),
            "sonar_state": sonar_summary.get("sonar_state"),
            "quality_gate": sonar_summary.get("quality_gate"),
            "bugs": sonar_summary.get("bugs"),
            "code_smells": sonar_summary.get("code_smells"),
            "coverage": sonar_summary.get("coverage"),
            "duplication_percentage": sonar_summary.get("duplication_percentage"),
            "cognitive_complexity": sonar_summary.get("cognitive_complexity"),
            "reliability_rating": sonar_summary.get("reliability_rating"),
            "maintainability_rating": sonar_summary.get("maintainability_rating"),
            "technical_debt_minutes": sonar_summary.get("technical_debt_minutes"),
            "lines_of_code": sonar_summary.get("lines_of_code"),
        }

    run = AnalysisRun(
        repository_id=db_repo.id,
        branch=default_branch,
        status="running",
        user_id=current_user.id,
        commit_sha=head_sha,
        analysis_scope="repository",
        contributor_login=None,
        triggered_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    if existing_analysis:
        existing_analysis.latest_commit_sha = head_sha
        existing_analysis.analysis_version = analysis_version
        existing_analysis.analysis_status = "running"
        existing_analysis.analyzed_at = None
        existing_analysis.force_reanalyzed = force_reanalyze
        existing_analysis.last_run_id = run.id
    else:
        db.add(RepositoryAnalysis(
            repository_id=db_repo.id,
            user_id=current_user.id,
            latest_commit_sha=head_sha,
            analysis_version=analysis_version,
            analysis_status="running",
            analyzed_at=None,
            results_path=None,
            force_reanalyzed=force_reanalyze,
            last_run_id=run.id,
        ))

    db.add(RecruiterCandidate(
        analysis_run_id=run.id,
        task_id=task_id,
        candidate_name=candidate_name,
        github_login=github_login,
        github_avatar_url=github_avatar_url,
    ))
    db.commit()

    background_tasks.add_task(
        background_analysis_task,
        run_id=run.id,
        repo_id=db_repo.id,
        repo_url=html_url,
        repo_name=repo_name,
        branch=default_branch,
        full_name=full_name,
        token=token,
        is_private=bool(repo_data.get("private")),
        current_user_id=current_user.id,
        user_role=current_user.role.value,
        analysis_scope="repository",
        contributor_login=None,
        touched_files=[],
    )

    logger.info(
        "Recruiter bulk scheduled run_id=%s repo=%s candidate=%s user_id=%s",
        run.id,
        full_name,
        candidate_name,
        current_user.id,
    )

    return {
        "scheduled": True,
        "candidate": candidate_name,
        "github_avatar_url": github_avatar_url,
        "repo_name": repo_name,
        "clone_path": "",
        "html_url": html_url,
        "default_branch": default_branch,
        "analysis_run_id": run.id,
        "analysis_status": run.status,
        "status": "force_reanalyzed" if force_reanalyze else "analyzed",
        "latest_commit_sha": head_sha,
        "analyzed_at": None,
        "analysis_version": analysis_version,
        "skill_score": None,
        "skill_score_level": "Unavailable",
        "sonar_health_score": None,
        "sonar_state": "pending",
        "quality_gate": None,
        "bugs": None,
        "code_smells": None,
        "coverage": None,
        "duplication_percentage": None,
        "cognitive_complexity": None,
        "reliability_rating": None,
        "maintainability_rating": None,
        "technical_debt_minutes": None,
        "lines_of_code": None,
    }
