import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from app.core.auth_utils import decrypt_github_token, require_role
from app.core.rate_limiter import limiter
from app.db.database import get_db
from app.db.models import User
from app.services.code_analysis_service import build_github_connect_payload
from app.services.github_client import refresh_github_access_token_for_user
from app.services.recruiter_analysis_service import schedule_recruiter_repo_analysis
from app.services.recruiter_bulk_import import _parse_repo_url, parse_candidate_upload
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/recruiter", tags=["recruiter-bulk"])
logger = logging.getLogger(__name__)


class BulkRepository(BaseModel):
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


class BulkAnalyzeResponse(BaseModel):
    repositories: list[BulkRepository]
    skipped: list[dict]


class PreviewRow(BaseModel):
    candidate_name: str
    repo_url: str
    full_name: str
    repo_name: str
    branch: str = "main"


class BulkPreviewResponse(BaseModel):
    rows: list[PreviewRow]
    skipped: list[dict]
    valid_count: int
    skipped_count: int


class CandidateConfirmRow(BaseModel):
    candidate_name: str = Field(..., min_length=1)
    repo_url: str = Field(..., min_length=8)
    branch: str = "main"


class BulkConfirmRequest(BaseModel):
    candidates: list[CandidateConfirmRow] = Field(..., min_length=1)
    force_reanalyze: bool = False


async def _resolve_recruiter_token(
    request: Request,
    db: Session,
    current_user: User,
) -> str:
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
    return token


async def _schedule_rows(
    *,
    rows: list[dict],
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session,
    current_user: User,
    force_reanalyze: bool,
) -> BulkAnalyzeResponse:
    token = await _resolve_recruiter_token(request, db, current_user)
    repositories: list[BulkRepository] = []
    skipped: list[dict] = []

    for row in rows:
        result = await schedule_recruiter_repo_analysis(
            db=db,
            background_tasks=background_tasks,
            current_user=current_user,
            token=token,
            candidate_name=row["candidate_name"],
            repo_url=row["repo_url"],
            full_name=row["full_name"],
            repo_name=row["repo_name"],
            branch=row.get("branch") or "main",
            force_reanalyze=force_reanalyze,
        )

        if result.get("reason"):
            skipped.append({
                "candidate_name": row["candidate_name"],
                "repo_name": row["repo_name"],
                "reason": result["reason"],
            })
            continue

        repositories.append(BulkRepository(
            candidate=result["candidate"],
            repo_name=result["repo_name"],
            clone_path=result.get("clone_path", ""),
            html_url=result["html_url"],
            default_branch=result["default_branch"],
            analysis_run_id=result.get("analysis_run_id"),
            analysis_status=result.get("analysis_status"),
            status=result.get("status"),
            latest_commit_sha=result.get("latest_commit_sha"),
            analyzed_at=result.get("analyzed_at"),
            analysis_version=result.get("analysis_version"),
            sonar_health_score=result.get("sonar_health_score"),
        ))

    return BulkAnalyzeResponse(repositories=repositories, skipped=skipped)


@router.post("/bulk-analyze/preview", response_model=BulkPreviewResponse)
@limiter.limit("10/minute")
async def bulk_analyze_preview(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(require_role(["recruiter"])),
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        rows, skipped = parse_candidate_upload(file.filename or "candidates.csv", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    preview_rows = [
        PreviewRow(
            candidate_name=row["candidate_name"],
            repo_url=row["repo_url"],
            full_name=row["full_name"],
            repo_name=row["repo_name"],
            branch=row.get("branch") or "main",
        )
        for row in rows
    ]

    if not preview_rows and not skipped:
        raise HTTPException(status_code=400, detail="The uploaded file has no candidate rows.")

    return BulkPreviewResponse(
        rows=preview_rows,
        skipped=skipped,
        valid_count=len(preview_rows),
        skipped_count=len(skipped),
    )


@router.post("/bulk-analyze/confirm", response_model=BulkAnalyzeResponse)
@limiter.limit("3/minute")
async def bulk_analyze_confirm(
    request: Request,
    payload: BulkConfirmRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["recruiter"])),
):
    rows: list[dict] = []
    skipped: list[dict] = []

    for index, candidate in enumerate(payload.candidates, start=1):
        candidate_name = candidate.candidate_name.strip()
        if not candidate_name:
            skipped.append({"row": index, "reason": "missing_candidate_name"})
            continue
        try:
            repo_meta = _parse_repo_url(candidate.repo_url.strip())
        except ValueError as exc:
            skipped.append({
                "row": index,
                "candidate_name": candidate_name,
                "repo_url": candidate.repo_url,
                "reason": str(exc),
            })
            continue

        rows.append({
            "candidate_name": candidate_name,
            "branch": (candidate.branch or "main").strip() or "main",
            **repo_meta,
        })

    if not rows:
        raise HTTPException(
            status_code=400,
            detail="No valid candidates to analyze. Fix the preview rows and try again.",
        )

    result = await _schedule_rows(
        rows=rows,
        request=request,
        background_tasks=background_tasks,
        db=db,
        current_user=current_user,
        force_reanalyze=payload.force_reanalyze,
    )
    result.skipped = skipped + result.skipped

    logger.info(
        "Recruiter bulk confirm finished scheduled=%d skipped=%d user_id=%s",
        len(result.repositories),
        len(result.skipped),
        current_user.id,
    )
    return result
