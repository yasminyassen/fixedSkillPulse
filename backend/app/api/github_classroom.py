import asyncio
import logging
import os
import tempfile
import subprocess
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.auth_utils import decrypt_github_token, require_role
from app.core.config import settings
from app.core.rate_limiter import limiter
from app.db.models import AnalysisRun, RecruiterCandidate, Repository, RepositoryAnalysis, User
from app.services.code_analysis_service import build_github_connect_payload
from app.services.github_client import get_branch_head_sha, refresh_github_access_token_for_user
from app.services.analysis_orchestrator import background_analysis_task
from app.services.sonarqube_score_service import build_sonar_repo_summary
from app.db.database import get_db
from sqlalchemy.orm import Session


router = APIRouter(prefix="/api/github-classroom", tags=["github-classroom"])
logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
_GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


class ClassroomAnalyzeRequest(BaseModel):
    organization: str = Field(..., min_length=2)
    assignment_prefix: str = Field(..., min_length=2)
    force_reanalyze: bool = False


class ClassroomRepository(BaseModel):
    candidate: str
    repo_name: str
    clone_path: str = ""
    html_url: str
    default_branch: str
    analysis_run_id: int | None = None
    analysis_status: str | None = None
    status: str | None = None
    latest_commit_sha: str | None = None
    analyzed_at: datetime | None = None
    analysis_version: str | None = None
    sonar_health_score: float | None = None


class ClassroomAnalyzeResponse(BaseModel):
    repositories: list[ClassroomRepository]
    skipped: list[dict]


def _extract_candidate(repo_name: str, prefix: str) -> str:
    suffix = repo_name[len(prefix):].lstrip("-_")
    return suffix or "unknown"


def _build_auth_clone_url(org: str, repo_name: str, token: str) -> str:
    safe_token = quote(token, safe="")
    return f"https://{safe_token}@github.com/{org}/{repo_name}.git"


def _is_rate_limit_response(response: httpx.Response) -> bool:
    if response.status_code != 403:
        return False
    remaining = response.headers.get("X-RateLimit-Remaining")
    return remaining == "0"


async def _fetch_all_org_repos(org: str, token: str) -> list[dict[str, Any]]:
    headers = {**_GITHUB_HEADERS, "Authorization": f"Bearer {token}"}
    repos: list[dict[str, Any]] = []
    page = 1

    async with httpx.AsyncClient(timeout=20.0) as client:
        while True:
            response = await client.get(
                f"{GITHUB_API_BASE}/orgs/{org}/repos",
                headers=headers,
                params={"per_page": 100, "page": page},
            )

            if response.status_code == 401:
                raise HTTPException(status_code=401, detail="Invalid GitHub token")
            if _is_rate_limit_response(response):
                raise HTTPException(
                    status_code=503,
                    detail="GitHub API rate limit reached. Please wait and try again.",
                )
            if response.status_code == 404:
                raise HTTPException(
                    status_code=404,
                    detail="Organization not found or inaccessible",
                )
            if not response.is_success:
                raise HTTPException(
                    status_code=502,
                    detail="GitHub API error while fetching repositories",
                )

            page_items = response.json() if isinstance(response.json(), list) else []
            if not page_items:
                break

            repos.extend(page_items)
            page += 1

    return repos


async def _clone_repo(
    org: str,
    repo_name: str,
    token: str,
    base_dir: str,
    semaphore: asyncio.Semaphore,
) -> str:
    async with semaphore:
        clone_path = os.path.join(base_dir, repo_name)
        auth_url = _build_auth_clone_url(org, repo_name, token)
        cmd = [
            "git",
            "clone",
            "--depth",
            "1",
            "--no-tags",
            "--filter=blob:none",
            auth_url,
            clone_path,
        ]
        await asyncio.to_thread(
            subprocess.run,
            cmd,
            check=True,
            timeout=300,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return clone_path


@router.post("/analyze", response_model=ClassroomAnalyzeResponse)
@limiter.limit("2/minute")
async def analyze_github_classroom(
    request: Request,
    payload: ClassroomAnalyzeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["recruiter"])),
):
    organization = payload.organization.strip()
    assignment_prefix = payload.assignment_prefix.strip()
    force_reanalyze = bool(payload.force_reanalyze)
    analysis_version = settings.analysis_version

    if not organization or not assignment_prefix:
        raise HTTPException(status_code=400, detail="All fields are required")

    if not current_user.github_access_token:
        raise HTTPException(
            status_code=403,
            detail=build_github_connect_payload(request, current_user),
        )

    token = decrypt_github_token(current_user.github_access_token)

    if (
        current_user.github_token_expires_at
        and current_user.github_token_expires_at <= datetime.now(timezone.utc)
    ):
        refreshed_token = await refresh_github_access_token_for_user(db, current_user)
        if refreshed_token:
            token = refreshed_token

    if not token:
        raise HTTPException(
            status_code=403,
            detail=build_github_connect_payload(request, current_user),
        )

    try:
        repos = await _fetch_all_org_repos(organization, token)
    except HTTPException as exc:
        if exc.status_code == 401:
            refreshed_token = await refresh_github_access_token_for_user(db, current_user)
            if refreshed_token:
                token = refreshed_token
                repos = await _fetch_all_org_repos(organization, token)
            else:
                raise HTTPException(
                    status_code=403,
                    detail=build_github_connect_payload(request, current_user),
                ) from exc
        else:
            raise
    assignment_repos = [
        repo for repo in repos
        if isinstance(repo.get("name"), str)
        and repo["name"].startswith(assignment_prefix)
    ]
    logger.info(
        "GitHub Classroom analysis scheduling started org=%s prefix=%s repos=%d user_id=%s",
        organization,
        assignment_prefix,
        len(assignment_repos),
        current_user.id,
    )

    repositories: list[ClassroomRepository] = []
    skipped: list[dict] = []

    for repo in assignment_repos:
        repo_name = repo.get("name")
        html_url = repo.get("html_url")
        full_name = repo.get("full_name") or f"{organization}/{repo_name}"
        default_branch = repo.get("default_branch") or "main"
        if not repo_name or not html_url:
            skipped.append({
                "repo_name": repo_name or "unknown",
                "reason": "missing_repository_metadata",
            })
            continue

        try:
            head_sha = await get_branch_head_sha(token, full_name, default_branch)
        except HTTPException as exc:
            skipped.append({
                "repo_name": repo_name,
                "reason": f"github_branch_lookup_failed_{exc.status_code}",
            })
            continue
        except Exception:
            skipped.append({
                "repo_name": repo_name,
                "reason": "github_branch_lookup_unexpected_error",
            })
            continue

        if not head_sha:
            skipped.append({
                "repo_name": repo_name,
                "reason": "branch_not_found",
            })
            continue

        db_repo = db.query(Repository).filter(Repository.github_repo_id == str(repo.get("id"))).first()
        if not db_repo:
            db_repo = Repository(
                name=repo_name,
                full_name=full_name,
                url=html_url,
                github_repo_id=str(repo.get("id")),
                is_private=bool(repo.get("private")),
            )
            db.add(db_repo)
            db.commit()
            db.refresh(db_repo)

        candidate_name = _extract_candidate(repo_name, assignment_prefix)

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
            existing_score = None
            if existing_analysis.last_run_id:
                existing_run = db.query(AnalysisRun).filter(AnalysisRun.id == existing_analysis.last_run_id).first()
                if existing_run:
                    existing_score = build_sonar_repo_summary(existing_run).get("sonar_health_score")

            status_label = "skipped_no_changes" if existing_analysis.analysis_status == "completed" else existing_analysis.analysis_status
            repositories.append(ClassroomRepository(
                candidate=candidate_name,
                repo_name=repo_name,
                clone_path="",
                html_url=html_url,
                default_branch=default_branch,
                analysis_run_id=existing_analysis.last_run_id,
                analysis_status=existing_analysis.analysis_status,
                status=status_label,
                latest_commit_sha=existing_analysis.latest_commit_sha,
                analyzed_at=existing_analysis.analyzed_at,
                analysis_version=existing_analysis.analysis_version,
                sonar_health_score=existing_score,
            ))
            continue

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
            candidate_name=candidate_name,
            github_login=None,
        ))
        db.commit()
        logger.info(
            "GitHub Classroom scheduled run_id=%s repo=%s branch=%s private=%s",
            run.id,
            full_name,
            default_branch,
            bool(repo.get("private")),
        )

        background_tasks.add_task(
            background_analysis_task,
            run_id=run.id,
            repo_id=db_repo.id,
            repo_url=html_url,
            repo_name=repo_name,
            branch=default_branch,
            full_name=full_name,
            token=token,
            is_private=bool(repo.get("private")),
            current_user_id=current_user.id,
            user_role=current_user.role.value,
            analysis_scope="repository",
            contributor_login=None,
            touched_files=[],
        )

        repositories.append(ClassroomRepository(
            candidate=candidate_name,
            repo_name=repo_name,
            clone_path="",
            html_url=html_url,
            default_branch=default_branch,
            analysis_run_id=run.id,
            analysis_status=run.status,
            status="force_reanalyzed" if force_reanalyze else "analyzed",
            latest_commit_sha=head_sha,
            analyzed_at=None,
            analysis_version=analysis_version,
        ))

    logger.info(
        "GitHub Classroom analysis scheduling finished scheduled=%d skipped=%d user_id=%s",
        len(repositories),
        len(skipped),
        current_user.id,
    )
    return ClassroomAnalyzeResponse(repositories=repositories, skipped=skipped)
