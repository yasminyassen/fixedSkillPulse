from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from jose import jwt
from passlib.exc import UnknownHashError
from passlib.context import CryptContext
from app.core.config import settings
import secrets
from app.db.database import get_db
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.db.models import User
import hmac
import hashlib
from cryptography.fernet import Fernet

http_bearer = HTTPBearer()

def oauth2_scheme(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    return credentials.credentials

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def has_usable_password_hash(hashed_password: str | None) -> bool:
    if not hashed_password:
        return False
    return pwd_context.identify(hashed_password) is not None

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not plain_password or not has_usable_password_hash(hashed_password):
        return False
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except (UnknownHashError, TypeError, ValueError):
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta is not None:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt

def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.JWTError:
        return None

def hash_refresh_token(raw_token: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(),
        raw_token.encode(),
        hashlib.sha256
    ).hexdigest()

def create_refresh_token():
    raw_token = secrets.token_urlsafe(64)
    hashed_token = hash_refresh_token(raw_token)
    return raw_token, hashed_token

# ── GitHub Token Encryption ───────────────────────────────────────────────────

def encrypt_github_token(token: str) -> str:
    """Encrypt GitHub access token before storing in DB."""
    f = Fernet(settings.ENCRYPTION_KEY.encode())
    return f.encrypt(token.encode()).decode()

def decrypt_github_token(encrypted_token: str) -> str:
    """Decrypt stored GitHub access token."""
    f = Fernet(settings.ENCRYPTION_KEY.encode())
    return f.decrypt(encrypted_token.encode()).decode()

# ── Auth Dependencies ─────────────────────────────────────────────────────────

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
    db: Session = Depends(get_db)):
    token = credentials.credentials

    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    user_id = payload.get("sub")

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )

    user = db.query(User).filter(User.id == int(user_id)).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    return user


def require_role(allowed_roles: list):
    def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role.value not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource"
            )
        return current_user
    return role_checker
