

import sys
import os
import secrets
from datetime import datetime, timedelta, timezone

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.db.database import get_db
from app.core.auth_utils import get_current_user, has_usable_password_hash, hash_password, verify_password
from app.db.models import (
    AnalysisRun,
    CodeMetrics,
    ProfileActivityLog,
    RecruiterCandidate,
    RepositoryAnalysis,
    RepositoryContributor,
    RequirementDocument,
    RefreshToken,
    SecurityFinding,
    SkillScore,
    SonarAnalysisSummary,
    SonarFileMeasure,
    SonarIssue,
    TechnicalTask,
    User,
    UserStory,
)
from app.schemas.profile_schemas import (
    ChangePasswordCodeRequest,
    ChangePasswordRequest,
    DeleteAccountRequest,
    MessageResponse,
    SetPasswordRequest,
)
from app.services.email_service import EmailDeliveryError, send_verification_email

router = APIRouter(prefix="/profile", tags=["profile"])




def _get_github_login(db: Session, user: User) -> Optional[str]:
    """
    The User model stores github_access_token (encrypted) but NOT a plain
    github_login column.  The login is written to AnalysisRun.contributor_login
    by resolve_github_identity() during analysis.  We read it from there.
    Returns None if GitHub is not connected or no analysis has been run yet.
    """
    if not user.github_access_token:
        return None
    run = (
        db.query(AnalysisRun.contributor_login)
        .filter(
            AnalysisRun.user_id == user.id,
            AnalysisRun.contributor_login.isnot(None),
        )
        .order_by(AnalysisRun.triggered_at.desc())
        .first()
    )
    return run.contributor_login if run else None


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




class ProfileResponse(BaseModel):
    id: int
    full_name: str
    username: str
    email: str
    role: Optional[str] = None
    avatar_url: Optional[str] = None
    github_login: Optional[str] = None
    github_connected: bool = False
    has_password: bool = False
    organization: Optional[str] = None
    department: Optional[str] = None
    job_title: Optional[str] = None
    member_since: Optional[str] = None

    class Config:
        from_attributes = True


class UpdateAccountRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    organization: Optional[str] = None
    department: Optional[str] = None
    job_title: Optional[str] = None




@router.get("", response_model=ProfileResponse)
async def get_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lightweight account info for the Account Settings page.
    Does NOT run any analytics queries.
    """
    github_login = _get_github_login(db, current_user)

    return ProfileResponse(
        id=current_user.id,
        full_name=current_user.full_name or "",
        username=current_user.username or "",
        email=current_user.work_email or "",
        role=current_user.role.value if current_user.role else None,
        avatar_url=current_user.avatar_url,
        github_login=github_login,
        github_connected=bool(current_user.github_access_token),
        has_password=has_usable_password_hash(current_user.hashed_password),
        organization=current_user.organization,
        department=current_user.department,
        job_title=current_user.job_title,
        member_since=current_user.created_at.isoformat() if current_user.created_at else None,
    )




@router.patch("")
async def update_profile(
    data: UpdateAccountRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update full_name, organization, and/or job_title."""
    changed: dict = {}

    if data.full_name is not None:
        v = data.full_name.strip()
        if not v:
            raise HTTPException(status_code=422, detail="full_name cannot be empty")
        current_user.full_name = v
        changed["full_name"] = v

    if data.email is not None:
        email = data.email.strip()
        if not email:
            raise HTTPException(status_code=422, detail="email cannot be empty")
        exists = db.query(User).filter(User.work_email == email, User.id != current_user.id).first()
        if exists:
            raise HTTPException(status_code=400, detail="Email already registered")
        current_user.work_email = email
        changed["email"] = email

    if data.avatar_url is not None:
        current_user.avatar_url = data.avatar_url.strip() or None
        changed["avatar_url"] = current_user.avatar_url

    if data.organization is not None:
        current_user.organization = data.organization.strip() or None
        changed["organization"] = current_user.organization

    if data.department is not None:
        current_user.department = data.department.strip() or None
        changed["department"] = current_user.department

    if data.job_title is not None:
        current_user.job_title = data.job_title.strip() or None
        changed["job_title"] = current_user.job_title

    if not changed:
        raise HTTPException(status_code=422, detail="No fields provided to update")

    db.commit()
    db.refresh(current_user)
    return {"message": "Profile updated successfully", **changed}


@router.post("/set-password/request-code", response_model=MessageResponse)
async def request_set_password_code(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if has_usable_password_hash(current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Account already has a password. Use change-password instead.")
    return await _send_account_code(current_user, db)


@router.post("/set-password", response_model=MessageResponse)
def set_password(
    data: SetPasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
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


@router.post("/change-password/request-code", response_model=MessageResponse)
async def request_change_password_code(
    data: ChangePasswordCodeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_password_login_configured(current_user)
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    return await _send_account_code(current_user, db)


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
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


def _delete_current_user(db: Session, current_user: User) -> MessageResponse:
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


@router.post("/delete-account", response_model=MessageResponse)
def delete_account_with_password(
    data: DeleteAccountRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if data.confirm_email.lower() != (current_user.work_email or "").lower():
        raise HTTPException(status_code=400, detail="Confirmation email does not match")
    _ensure_password_login_configured(current_user)
    if not verify_password(data.password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Password is incorrect")
    return _delete_current_user(db, current_user)


@router.delete("")
async def delete_account(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _delete_current_user(db, current_user)
