import sys
import os
import secrets
from datetime import datetime, timedelta, timezone

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional

from app.db.database import get_db
from app.db.models import (
    AnalysisRun,
    CodeMetrics,
    ProfileActivityLog,
    RecruiterCandidate,
    RefreshToken,
    Repository,
    RepositoryAnalysis,
    RepositoryContributor,
    RequirementDocument,
    SecurityFinding,
    SkillScore,
    SonarAnalysisSummary,
    SonarFileMeasure,
    SonarIssue,
    TechnicalTask,
    User,
    UserStory,
)
from app.core.auth_utils import (
    get_current_user,
    has_usable_password_hash,
    hash_password,
    require_role,
    verify_password,
)
from app.schemas.profile_schemas import (
    ChangePasswordCodeRequest,
    ChangePasswordRequest,
    DeleteAccountRequest,
    MessageResponse,
    SetPasswordRequest,
)
from app.services.email_service import EmailDeliveryError, send_verification_email
from app.services.sonarqube_score_service import build_skill_score_fields, build_sonar_repo_summary

router = APIRouter(prefix="/recruiter", tags=["recruiter"])


def _require_recruiter(current_user: User) -> User:
    if not current_user.role or current_user.role.value != "recruiter":
        raise HTTPException(status_code=403, detail="Recruiter access required.")
    return current_user


class UpdateRecruiterProfileRequest(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    avatar_url: Optional[str] = Field(default=None, max_length=500)
    organization: Optional[str] = None
    job_title:    Optional[str] = None
    department:   Optional[str] = None
    hiring_focus: Optional[str] = None


class UpdateEvalSettingsRequest(BaseModel):
    security_score_visible:  Optional[bool] = None
    high_priority_threshold: Optional[int]  = None
    weight_code_quality:     Optional[int]  = None
    weight_architecture:     Optional[int]  = None
    weight_maintainability:  Optional[int]  = None
    weight_security:         Optional[int]  = None
    weight_git_activity:     Optional[int]  = None


def _recruiter_profile_payload(current_user: User) -> dict:
    return {
        "id": current_user.id,
        "full_name": current_user.full_name or "",
        "username": current_user.username or "",
        "email": current_user.work_email or "",
        "role": current_user.role.value if current_user.role else None,
        "avatar_url": current_user.avatar_url,
        "github_connected": bool(current_user.github_access_token),
        "has_password": has_usable_password_hash(current_user.hashed_password),
        "organization": current_user.organization,
        "job_title": current_user.job_title,
        "department": current_user.department,
        "hiring_focus": current_user.hiring_focus,
        "member_since": current_user.created_at.isoformat() if current_user.created_at else None,
        "security_score_visible": current_user.security_score_visible if current_user.security_score_visible is not None else True,
        "high_priority_threshold": current_user.high_priority_threshold if current_user.high_priority_threshold is not None else 75,
        "weight_code_quality": current_user.weight_code_quality if current_user.weight_code_quality is not None else 20,
        "weight_architecture": current_user.weight_architecture if current_user.weight_architecture is not None else 20,
        "weight_maintainability": current_user.weight_maintainability if current_user.weight_maintainability is not None else 20,
        "weight_security": current_user.weight_security if current_user.weight_security is not None else 20,
        "weight_git_activity": current_user.weight_git_activity if current_user.weight_git_activity is not None else 20,
    }


def _ensure_password_login_configured(current_user: User) -> None:
    if has_usable_password_hash(current_user.hashed_password):
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            "This account does not have a usable password hash. "
            "Set a password first or use the forgot-password flow."
        ),
    )


def _verification_code_is_valid(current_user: User, code: str) -> bool:
    expires_at = current_user.reset_password_expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return bool(
        current_user.verification_code
        and current_user.verification_code == code
        and expires_at
        and expires_at >= datetime.now(timezone.utc)
    )


async def _send_account_code(current_user: User, db: Session) -> MessageResponse:
    code = f"{secrets.randbelow(1_000_000):06d}"
    current_user.verification_code = code
    current_user.reset_password_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    db.commit()

    try:
        await send_verification_email(current_user.work_email, code)
    except EmailDeliveryError:
        return MessageResponse(
            message="Email delivery failed; use the returned verification code for local testing",
            data={"verification_code": code, "email_delivery": "failed"},
        )

    return MessageResponse(message="Verification code sent to your email")


@router.get("/profile")
async def get_recruiter_profile(
    current_user: User = Depends(require_role(["recruiter"])),
):
    return _recruiter_profile_payload(current_user)


@router.patch("/profile")
async def update_recruiter_profile(
    data: UpdateRecruiterProfileRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_recruiter(current_user)

    if data.full_name is not None:
        current_user.full_name = data.full_name.strip()
    if data.email is not None:
        email = str(data.email).strip()
        if email != current_user.work_email:
            exists = db.query(User).filter(User.work_email == email, User.id != current_user.id).first()
            if exists:
                raise HTTPException(status_code=400, detail="Email already registered")
            current_user.work_email = email
    if data.avatar_url is not None:
        current_user.avatar_url = data.avatar_url.strip() or None
    if data.organization is not None:
        current_user.organization = data.organization.strip() or None
    if data.job_title is not None:
        current_user.job_title = data.job_title.strip() or None
    if data.department is not None:
        current_user.department = data.department.strip() or None
    if data.hiring_focus is not None:
        current_user.hiring_focus = data.hiring_focus.strip() or None

    db.commit()
    db.refresh(current_user)

    return _recruiter_profile_payload(current_user)


@router.post("/profile/set-password/request-code", response_model=MessageResponse)
async def request_recruiter_set_password_code(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["recruiter"])),
):
    if has_usable_password_hash(current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Account already has a password. Use change-password instead.")
    return await _send_account_code(current_user, db)


@router.post("/profile/set-password", response_model=MessageResponse)
def set_recruiter_password(
    data: SetPasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["recruiter"])),
):
    if has_usable_password_hash(current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Account already has a password. Use change-password instead.")
    if not _verification_code_is_valid(current_user, data.verification_code):
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")

    current_user.hashed_password = hash_password(data.new_password)
    current_user.verification_code = None
    current_user.reset_password_expires_at = None
    db.commit()
    return MessageResponse(message="Password set successfully")


@router.post("/profile/change-password/request-code", response_model=MessageResponse)
async def request_recruiter_password_change_code(
    data: ChangePasswordCodeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["recruiter"])),
):
    _ensure_password_login_configured(current_user)
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    return await _send_account_code(current_user, db)


@router.post("/profile/change-password", response_model=MessageResponse)
def change_recruiter_password(
    data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["recruiter"])),
):
    _ensure_password_login_configured(current_user)
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if data.current_password == data.new_password:
        raise HTTPException(status_code=400, detail="New password must be different")
    if not _verification_code_is_valid(current_user, data.verification_code):
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")

    current_user.hashed_password = hash_password(data.new_password)
    current_user.verification_code = None
    current_user.reset_password_expires_at = None
    db.commit()
    return MessageResponse(message="Password changed successfully")


def _delete_recruiter_account(db: Session, current_user: User) -> MessageResponse:
    user_id = current_user.id
    run_ids = [row.id for row in db.query(AnalysisRun.id).filter(AnalysisRun.user_id == user_id).all()]

    if run_ids:
        db.query(RepositoryAnalysis).filter(RepositoryAnalysis.last_run_id.in_(run_ids)).update(
            {RepositoryAnalysis.last_run_id: None},
            synchronize_session=False,
        )
        db.query(RecruiterCandidate).filter(RecruiterCandidate.analysis_run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(CodeMetrics).filter(CodeMetrics.analysis_run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(SecurityFinding).filter(SecurityFinding.analysis_run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(SonarIssue).filter(SonarIssue.analysis_run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(SonarFileMeasure).filter(SonarFileMeasure.analysis_run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(SonarAnalysisSummary).filter(SonarAnalysisSummary.analysis_run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(SkillScore).filter(SkillScore.analysis_run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(AnalysisRun).filter(AnalysisRun.id.in_(run_ids)).delete(synchronize_session=False)

    uploaded_doc_ids = [
        row.id
        for row in db.query(RequirementDocument.id)
        .filter(RequirementDocument.uploaded_by_id == user_id)
        .all()
    ]
    if uploaded_doc_ids:
        story_ids = [
            row.id
            for row in db.query(UserStory.id)
            .filter(UserStory.document_id.in_(uploaded_doc_ids))
            .all()
        ]
        if story_ids:
            db.query(TechnicalTask).filter(TechnicalTask.story_id.in_(story_ids)).delete(synchronize_session=False)
            db.query(UserStory).filter(UserStory.id.in_(story_ids)).delete(synchronize_session=False)
        db.query(RequirementDocument).filter(RequirementDocument.id.in_(uploaded_doc_ids)).delete(synchronize_session=False)

    db.query(TechnicalTask).filter(TechnicalTask.assigned_to == user_id).update(
        {TechnicalTask.assigned_to: None},
        synchronize_session=False,
    )
    db.query(RepositoryAnalysis).filter(RepositoryAnalysis.user_id == user_id).delete(synchronize_session=False)
    db.query(RepositoryContributor).filter(RepositoryContributor.user_id == user_id).delete(synchronize_session=False)
    db.query(RefreshToken).filter(RefreshToken.user_id == user_id).delete(synchronize_session=False)
    db.query(SkillScore).filter(SkillScore.user_id == user_id).delete(synchronize_session=False)
    db.query(ProfileActivityLog).filter(ProfileActivityLog.manager_id == user_id).delete(synchronize_session=False)
    db.query(ProfileActivityLog).filter(ProfileActivityLog.actor_id == user_id).update(
        {ProfileActivityLog.actor_id: None},
        synchronize_session=False,
    )
    db.query(ProfileActivityLog).filter(ProfileActivityLog.member_id == user_id).update(
        {ProfileActivityLog.member_id: None},
        synchronize_session=False,
    )

    db.delete(current_user)
    db.commit()
    return MessageResponse(message="Account deleted successfully")


@router.post("/profile/delete-account", response_model=MessageResponse)
def delete_recruiter_account(
    data: DeleteAccountRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["recruiter"])),
):
    if data.confirm_email.lower() != (current_user.work_email or "").lower():
        raise HTTPException(status_code=400, detail="Confirmation email does not match")
    _ensure_password_login_configured(current_user)
    if not verify_password(data.password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Password is incorrect")
    return _delete_recruiter_account(db, current_user)


@router.patch("/eval-settings")
async def update_eval_settings(
    data: UpdateEvalSettingsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_recruiter(current_user)

    if data.security_score_visible is not None:
        current_user.security_score_visible = data.security_score_visible

    if data.high_priority_threshold is not None:
        if not (0 <= data.high_priority_threshold <= 100):
            raise HTTPException(status_code=422, detail="high_priority_threshold must be 0–100")
        current_user.high_priority_threshold = data.high_priority_threshold

    for field, val in [
        ("weight_code_quality", data.weight_code_quality),
        ("weight_architecture", data.weight_architecture),
        ("weight_maintainability", data.weight_maintainability),
        ("weight_security",     data.weight_security),
        ("weight_git_activity", data.weight_git_activity),
    ]:
        if val is not None:
            if not (0 <= val <= 100):
                raise HTTPException(status_code=422, detail=f"{field} must be 0–100")
            setattr(current_user, field, val)

    db.commit()
    db.refresh(current_user)

    return {
        "security_score_visible":  current_user.security_score_visible,
        "high_priority_threshold": current_user.high_priority_threshold,
        "weight_code_quality":     current_user.weight_code_quality,
        "weight_architecture":     current_user.weight_architecture,
        "weight_maintainability":  current_user.weight_maintainability,
        "weight_security":         current_user.weight_security,
        "weight_git_activity":     current_user.weight_git_activity,
    }


@router.delete("/candidates/{run_id}")
async def delete_candidate(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_recruiter(current_user)

    candidate = (
        db.query(RecruiterCandidate)
        .join(AnalysisRun, RecruiterCandidate.analysis_run_id == AnalysisRun.id)
        .filter(
            RecruiterCandidate.analysis_run_id == run_id,
            AnalysisRun.user_id == current_user.id,
        )
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    run = db.query(AnalysisRun).filter(AnalysisRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found.")

    db.query(RepositoryAnalysis).filter(
        RepositoryAnalysis.last_run_id == run_id
    ).update({"last_run_id": None}, synchronize_session="fetch")

    db.query(RecruiterCandidate).filter(
        RecruiterCandidate.analysis_run_id == run_id
    ).delete(synchronize_session="fetch")

    db.query(SonarIssue).filter(SonarIssue.analysis_run_id == run_id).delete(synchronize_session=False)
    db.query(SonarFileMeasure).filter(SonarFileMeasure.analysis_run_id == run_id).delete(synchronize_session=False)
    db.query(SonarAnalysisSummary).filter(SonarAnalysisSummary.analysis_run_id == run_id).delete(synchronize_session=False)

    db.delete(run)
    db.commit()

    return {"message": "Candidate analysis deleted successfully."}


@router.get("/profile-dashboard")
async def get_recruiter_profile_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_recruiter(current_user)

    user_block = {
        "id":                      current_user.id,
        "full_name":               current_user.full_name,
        "username":                current_user.username,
        "email":                   current_user.work_email,
        "role":                    current_user.role.value if current_user.role else None,
        "avatar_url":              current_user.avatar_url,
        "organization":            current_user.organization,
        "job_title":               current_user.job_title,
        "department":              current_user.department,
        "hiring_focus":            current_user.hiring_focus,
        "member_since":            current_user.created_at.isoformat() if current_user.created_at else None,
        "github_connected":        bool(current_user.github_access_token),
        "has_password":            has_usable_password_hash(current_user.hashed_password),
        "security_score_visible":  current_user.security_score_visible  if current_user.security_score_visible  is not None else True,
        "high_priority_threshold": current_user.high_priority_threshold if current_user.high_priority_threshold is not None else 75,
        "weight_code_quality":     current_user.weight_code_quality     if current_user.weight_code_quality     is not None else 20,
        "weight_architecture":     current_user.weight_architecture     if current_user.weight_architecture     is not None else 20,
        "weight_maintainability":  current_user.weight_maintainability  if current_user.weight_maintainability  is not None else 20,
        "weight_security":         current_user.weight_security         if current_user.weight_security         is not None else 20,
        "weight_git_activity":     current_user.weight_git_activity     if current_user.weight_git_activity     is not None else 20,
    }

    candidates_evaluated = (
        db.query(func.count(func.distinct(RecruiterCandidate.candidate_name)))
        .join(AnalysisRun, RecruiterCandidate.analysis_run_id == AnalysisRun.id)
        .filter(AnalysisRun.user_id == current_user.id, AnalysisRun.status == "completed")
        .scalar()
    ) or 0

    latest_run_per_candidate = (
        db.query(func.max(AnalysisRun.id))
        .join(RecruiterCandidate, RecruiterCandidate.analysis_run_id == AnalysisRun.id)
        .filter(
            AnalysisRun.user_id == current_user.id,
            AnalysisRun.status == "completed",
        )
        .group_by(RecruiterCandidate.candidate_name)
        .subquery()
    )

    latest_candidate_runs = (
        db.query(AnalysisRun)
        .filter(
            AnalysisRun.id.in_(latest_run_per_candidate),
            AnalysisRun.user_id == current_user.id,
            AnalysisRun.status == "completed",
        )
        .all()
    )

    priority_threshold = current_user.high_priority_threshold if current_user.high_priority_threshold is not None else 75
    candidate_score_rows = {
        score.analysis_run_id: score
        for score in db.query(SkillScore)
        .filter(SkillScore.analysis_run_id.in_([run.id for run in latest_candidate_runs]))
        .all()
    }
    sonar_scores = [build_sonar_repo_summary(run)["sonar_health_score"] for run in latest_candidate_runs]
    skill_scores = [
        build_skill_score_fields(
            candidate_score_rows.get(run.id),
            sonar_health_score=build_sonar_repo_summary(run)["sonar_health_score"],
            security_score=getattr(candidate_score_rows.get(run.id), "security_awareness_score", None),
        )["skill_score"]
        for run in latest_candidate_runs
    ]

    high_priority_count = sum(
        1 for skill_score in skill_scores
        if skill_score is not None and skill_score >= priority_threshold
    )

    shortlisted_count = sum(
        1 for skill_score in skill_scores
        if skill_score is not None and skill_score >= 65
    )

    recent_runs = (
        db.query(AnalysisRun, Repository, RecruiterCandidate)
        .join(Repository, AnalysisRun.repository_id == Repository.id)
        .join(RecruiterCandidate, RecruiterCandidate.analysis_run_id == AnalysisRun.id)
        .filter(
            AnalysisRun.user_id == current_user.id,
            AnalysisRun.status == "completed",
            AnalysisRun.id.in_(latest_run_per_candidate),
        )
        .order_by(AnalysisRun.completed_at.desc())
        .limit(8)
        .all()
    )

    recent_activity = []
    for run, repo, candidate in recent_runs:
        sonar_summary = build_sonar_repo_summary(run)
        sonar_health_score = sonar_summary["sonar_health_score"]
        score_row = candidate_score_rows.get(run.id)
        skill_fields = build_skill_score_fields(
            score_row,
            sonar_health_score=sonar_health_score,
            security_score=getattr(score_row, "security_awareness_score", None),
        )
        recent_activity.append({
            "type":           "candidate_evaluated",
            "title":          "Candidate evaluated",
            "description":    (
                f"{candidate.candidate_name} - Skill Score: {skill_fields['skill_score']}"
                if skill_fields["skill_score"] is not None else f"{candidate.candidate_name} - score unavailable"
            ),
            "candidate_name": candidate.candidate_name,
            "repo_name":      repo.name,
            **skill_fields,
            "sonar_health_score": sonar_health_score,
            "sonar_state": sonar_summary["sonar_state"],
            "quality_gate": sonar_summary["quality_gate"],
            "run_id":         run.id,
            "completed_at":   run.completed_at.isoformat() if run.completed_at else None,
        })

    return {
        "user": user_block,
        "talent_overview": {
            "candidates_evaluated": candidates_evaluated,
            "high_priority":        high_priority_count,
            "profiles_shortlisted": shortlisted_count,
        },
        "recent_activity": recent_activity,
    }
