from operator import or_
import hashlib
import hmac
import logging
import re
import secrets
from fastapi import APIRouter, Depends, HTTPException, Response, Cookie , status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field, validator
from app.db.database import get_db
from app.db.models import User, RefreshToken
from app.core.auth_utils import hash_password, verify_password, create_access_token, create_refresh_token, hash_refresh_token, decode_access_token, get_current_user
from passlib.hash import argon2
from app.db.models import UserRole, DeveloperSpecialization
from app.core.config import settings
from datetime import datetime, timedelta, timezone
from fastapi import Request
from slowapi.util import get_remote_address
from app.core.rate_limiter import limiter
from app.services.email_service import EmailDeliveryError, send_reset_password_email, send_verification_email
from typing import Optional

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)
FORGOT_PASSWORD_SUCCESS_MESSAGE = "If that email is registered, a reset link has been sent"
RESET_PASSWORD_TOKEN_MINUTES = 30


def _cookie_samesite() -> str:
    raw = (settings.COOKIE_SAMESITE or "lax").strip().lower()
    return raw if raw in {"lax", "strict", "none"} else "lax"


def _cookie_secure() -> bool:
    # In production, always use secure cookies unless explicitly overridden.
    return settings.ENVIRONMENT == "production" or bool(settings.COOKIE_SECURE)


def _validate_password_strength(password: str) -> str:
    if not re.search(r"\d", password):
        raise ValueError('Password must contain at least one digit (0-9)')
    if not re.search(r"[A-Z]", password):
        raise ValueError('Password must contain at least one uppercase letter (A-Z)')
    if not re.search(r"[a-z]", password):
        raise ValueError('Password must contain at least one lowercase letter (a-z)')
    if not re.search(r"[ !@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password):
        raise ValueError('Password must contain at least one special character (@#$%...)')
    return password


def _hash_reset_password_token(raw_token: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(),
        raw_token.encode(),
        hashlib.sha256,
    ).hexdigest()


def _is_expired(expires_at: datetime) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at < datetime.now(timezone.utc)

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=20, pattern=r"^[a-zA-Z0-9_-]+$")
    full_name: str = Field(..., min_length=3, max_length=100)
    work_email: EmailStr
    role: UserRole
    specialization: Optional[DeveloperSpecialization] = None
    
    password: str = Field(..., min_length=8)

    
    @validator('full_name')
    def name_must_not_be_empty(cls, v):
        if not v.strip():
            raise ValueError('Full name cannot be empty spaces')
        return v.title()
    @validator('password')
    def password_strength(cls, v):
        return _validate_password_strength(v)
    
    @validator('specialization', always=True)
    def check_specialization(cls, v, values):
        role = values.get('role')
        if role == UserRole.developer and not v:
            raise ValueError('Specialization is required for developers')
        if role != UserRole.developer:
            return None 
        return v

class ProfileComplete(BaseModel):
    role: UserRole
    specialization: Optional[DeveloperSpecialization] = None

    @validator('specialization', always=True)
    def check_specialization(cls, v, values):
        role = values.get('role')
        if role == UserRole.developer and not v:
            raise ValueError('Specialization is required for developers')
        if role != UserRole.developer:
            return None
        return v

class UserLogin(BaseModel):
    username: str
    password: str

class EmailVerify(BaseModel):
    work_email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=32)
    new_password: str = Field(..., min_length=8)

    @validator('new_password')
    def password_strength(cls, v):
        return _validate_password_strength(v)

class Token(BaseModel):
    access_token: str
    token_type: str

class RoleUpdate(BaseModel):
        role: UserRole


@router.patch("/role")
def update_role(data: RoleUpdate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.role = data.role
    db.commit()
    return {"message": "Role updated", "role": data.role.value}

@router.patch("/complete-profile")
def complete_profile(data: ProfileComplete, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.role = data.role
    current_user.specialization = data.specialization
    db.commit()
    db.refresh(current_user)
    return {
        "message": "Profile completed successfully", 
        "role": current_user.role.value, 
        "specialization": current_user.specialization.value if current_user.specialization else None
    }


@router.get("/whoami-full")
def whoami_full(current_user=Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "full_name": current_user.full_name,
        "work_email": current_user.work_email,
        "avatar_url": getattr(current_user, "avatar_url", None),
        "role": current_user.role.value if current_user.role else None,
        "specialization": current_user.specialization.value if getattr(current_user, "specialization", None) else None
    }


@router.post("/register")
@limiter.limit("3/minute")
async def register(request: Request, user: UserRegister, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == user.username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    if db.query(User).filter(User.work_email == user.work_email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    verification_code = f"{secrets.randbelow(1_000_000):06d}"

    new_user = User(
        full_name=user.full_name,
        username=user.username,
        work_email=user.work_email,
        hashed_password=hash_password(user.password),
        role=user.role,
        specialization=user.specialization,
        is_verified=False,
        verification_code=verification_code,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    try:
        await send_verification_email(user.work_email, verification_code)
    except EmailDeliveryError:
        db.delete(new_user)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to send verification email. Please try again later.",
        )

    return {
        "message": "User registered successfully. Please verify your email.",
        "user_id": new_user.id,
        "work_email": new_user.work_email,
    }


@router.post("/verify-email")
@limiter.limit("10/minute")
def verify_email(request: Request, data: EmailVerify, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.work_email == data.work_email).first()
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if db_user.is_verified:
        return {"message": "Email already verified"}

    if db_user.verification_code != data.code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")

    db_user.is_verified = True
    db_user.verification_code = None
    db.commit()

    return {"message": "Email verified successfully"}


@router.post("/forgot-password")
@limiter.limit("5/minute")
async def forgot_password(request: Request, data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.work_email.ilike(data.email)).first()

    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found with this email address.",
        )

    raw_token = secrets.token_urlsafe(48)
    db_user.reset_password_token = _hash_reset_password_token(raw_token)
    db_user.reset_password_expires_at = datetime.now(timezone.utc) + timedelta(minutes=RESET_PASSWORD_TOKEN_MINUTES)
    db.commit()

    try:
        await send_reset_password_email(db_user.work_email, raw_token)
    except EmailDeliveryError:
        logger.exception("Failed to send password reset email to %s", db_user.work_email)
        db_user.reset_password_token = None
        db_user.reset_password_expires_at = None
        db.commit()

    return {"message": FORGOT_PASSWORD_SUCCESS_MESSAGE}


@router.post("/reset-password")
@limiter.limit("5/minute")
def reset_password(request: Request, data: ResetPasswordRequest, db: Session = Depends(get_db)):
    hashed_token = _hash_reset_password_token(data.token)
    db_user = db.query(User).filter(User.reset_password_token == hashed_token).first()

    if (
        not db_user
        or not db_user.reset_password_expires_at
        or _is_expired(db_user.reset_password_expires_at)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    db_user.hashed_password = hash_password(data.new_password)
    db_user.reset_password_token = None
    db_user.reset_password_expires_at = None
    db.commit()

    return {"message": "Password reset successfully"}


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
def login(
    request: Request,
    user: UserLogin,
    response: Response,
    db: Session = Depends(get_db)
):
    db_user = db.query(User).filter(
        or_(User.username == user.username, User.work_email.ilike( user.username))
    ).first()
    
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=400, detail="Invalid credentials")

    if not db_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before logging in",
        )

    access_token = create_access_token(
        data={
            "sub": str(db_user.id),
            "role": db_user.role.value
        },
        expires_delta=timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    )

    raw_refresh_token, hashed_refresh_token = create_refresh_token()
    refresh_expires = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )

    db_refresh = RefreshToken(
        token=hashed_refresh_token,
        user_id=db_user.id,
        expires_at=refresh_expires
    )

    db.add(db_refresh)
    db.commit()

    response.set_cookie(
        key="refresh_token",
        value=raw_refresh_token,
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }
    

@router.post("/refresh")
def refresh(
    response: Response,
    refresh_token: str = Cookie(None),
    db: Session = Depends(get_db)
):

    if not refresh_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    

    # Cleanup expired tokens
    db.query(RefreshToken).filter(
        RefreshToken.expires_at < datetime.now(timezone.utc)
    ).delete()
    db.commit()

    hashed_incoming = hash_refresh_token(refresh_token)

    db_token = db.query(RefreshToken).filter(
        RefreshToken.token == hashed_incoming
    ).first()

    if not db_token:
        # Possible reuse attack
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    # Check if expired
    if db_token.expires_at < datetime.now(timezone.utc):
        db.delete(db_token)
        db.commit()
        raise HTTPException(status_code=401, detail="Refresh token expired")

    user_id = db_token.user_id

    # Token Rotation
    db.delete(db_token)

    new_raw_refresh_token, new_hashed_refresh_token = create_refresh_token()
    new_expiry = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )

    new_db_token = RefreshToken(
        token=new_hashed_refresh_token,
        user_id=user_id,
        expires_at=new_expiry
    )

    db.add(new_db_token)
    db.commit()

    # Create new access token
    user = db.query(User).filter(User.id == user_id).first()

    new_access_token = create_access_token(
        data={
            "sub": str(user_id),
            "role": user.role.value
        },
        expires_delta=timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    )

    # Update Cookie
    response.set_cookie(
        key="refresh_token",
        value=new_raw_refresh_token,
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    )

    return {
        "access_token": new_access_token,
        "token_type": "bearer"
    }

@router.post("/logout")
def logout(
    response: Response,
    refresh_token: str = Cookie(None),
    db: Session = Depends(get_db)
):

    if refresh_token:
        hashed_incoming = hash_refresh_token(refresh_token)

        db_token = db.query(RefreshToken).filter(
            RefreshToken.token == hashed_incoming
        ).first()

        if db_token:
            db.delete(db_token)
            db.commit()

    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite()
    )

    return {"message": "Logged out successfully"}


@router.get("/whoami")
def who_am_i(current_user = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role.value if current_user.role else None
    }
