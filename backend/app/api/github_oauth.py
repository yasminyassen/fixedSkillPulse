from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import User, RefreshToken, UserRole
from app.core.auth_utils import create_access_token, create_refresh_token, encrypt_github_token, decode_access_token
from app.core.config import settings
from datetime import datetime, timedelta, timezone
import httpx
from fastapi import Request
from app.core.rate_limiter import limiter
from fastapi.responses import RedirectResponse
from urllib.parse import urlencode

router = APIRouter(prefix="/auth", tags=["github"])

GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAIL_URL = "https://api.github.com/user/emails"
GITHUB_OAUTH_TIMEOUT = httpx.Timeout(20.0, connect=10.0, read=20.0)


def _cookie_samesite() -> str:
    raw = (settings.COOKIE_SAMESITE or "lax").strip().lower()
    return raw if raw in {"lax", "strict", "none"} else "lax"


def _cookie_secure() -> bool:
    return settings.ENVIRONMENT == "production" or bool(settings.COOKIE_SECURE)


def _frontend_base_url() -> str:
    return settings.FRONTEND_URL.rstrip("/")


def _frontend_oauth_error(code: str, message: str) -> RedirectResponse:
    query = urlencode({"error": code, "message": message})
    return RedirectResponse(url=f"{_frontend_base_url()}/auth/github/callback?{query}")


def _expires_at_from_seconds(seconds: int | None) -> datetime | None:
    if seconds is None:
        return None

    safe_seconds = max(int(seconds) - 30, 0)
    return datetime.now(timezone.utc) + timedelta(seconds=safe_seconds)

@router.get("/github")
@limiter.limit("5/minute")
def github_login(request: Request, action: str = "login", token: str | None = None):
    """Redirect URL to send user to GitHub OAuth"""
    state = f"{action}:{token}" if token else action
    github_auth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={settings.GITHUB_CLIENT_ID}"
        f"&redirect_uri={settings.GITHUB_REDIRECT_URI}"
        f"&scope=user:email,repo,read:org"
        f"&state={state}"
    )
    return RedirectResponse(github_auth_url)
    #return {"url": github_auth_url}


@router.get("/github/callback")
@limiter.limit("5/minute")
async def github_callback(
    request: Request,
    code: str,
    state: str = "login",
    db: Session = Depends(get_db)
):
    """Exchange GitHub code for access token and log user in"""

    # 1. Exchange code for GitHub access token
    try:
        async with httpx.AsyncClient(timeout=GITHUB_OAUTH_TIMEOUT) as client:
            token_res = await client.post(
                GITHUB_TOKEN_URL,
                headers={"Accept": "application/json"},
                data={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": settings.GITHUB_REDIRECT_URI,
                },
            )
            token_data = token_res.json()
    except httpx.TimeoutException:
        return _frontend_oauth_error("github_timeout", "GitHub request timed out. Please try again.")
    except httpx.HTTPError:
        return _frontend_oauth_error("github_unreachable", "Unable to reach GitHub. Please try again.")

    github_access_token = token_data.get("access_token")
    if not github_access_token:
        return _frontend_oauth_error("github_oauth_failed", "GitHub authorization failed. Please try again.")

    github_refresh_token = token_data.get("refresh_token")
    github_token_expires_at = _expires_at_from_seconds(token_data.get("expires_in"))
    github_refresh_token_expires_at = _expires_at_from_seconds(token_data.get("refresh_token_expires_in"))

    # 2. Get GitHub user info
    try:
        async with httpx.AsyncClient(timeout=GITHUB_OAUTH_TIMEOUT) as client:
            user_res = await client.get(
                GITHUB_USER_URL,
                headers={"Authorization": f"Bearer {github_access_token}"},
            )
            github_user = user_res.json()

            email_res = await client.get(
                GITHUB_EMAIL_URL,
                headers={"Authorization": f"Bearer {github_access_token}"},
            )
            emails = email_res.json()
    except httpx.TimeoutException:
        return _frontend_oauth_error("github_timeout", "GitHub request timed out. Please try again.")
    except httpx.HTTPError:
        return _frontend_oauth_error("github_unreachable", "Unable to reach GitHub. Please try again.")

    github_id = str(github_user.get("id"))
    username = github_user.get("login")
    full_name = github_user.get("name") or username
    avatar_url = github_user.get("avatar_url")

    # Get primary verified email
    work_email = None
    if isinstance(emails, list):
        for e in emails:
            if e.get("primary") and e.get("verified"):
                work_email = e.get("email")
                break

    if not work_email:
        return _frontend_oauth_error("no_verified_email", "No verified email was found on this GitHub account.")

    # Encrypt token before storing
    encrypted_token = encrypt_github_token(github_access_token)
    encrypted_refresh_token = encrypt_github_token(github_refresh_token) if github_refresh_token else None

    # 3. Find or create user
    db_user = db.query(User).filter(User.github_id == github_id).first()
    # ── CONNECT FLOW ─────────────────────
    if ":" in state:
        action, token = state.split(":", 1)
    else:
        action = state
        token = None
    if action == "connect":

        if not token:
            return _frontend_oauth_error("missing_session", "Your session expired before GitHub could be connected. Please sign in and try again.")

        payload = decode_access_token(token)

        if not payload:
            return _frontend_oauth_error("invalid_session", "Your session expired before GitHub could be connected. Please sign in and try again.")

        user_id = payload.get("sub")

        current_user = db.query(User).filter(User.id == int(user_id)).first()

        if not current_user:
            return _frontend_oauth_error("user_not_found", "We could not find your SkillPulse account. Please sign in again.")

        existing = db.query(User).filter(User.github_id == github_id).first()

        if existing and existing.id != current_user.id:
            return _frontend_oauth_error(
                "github_already_linked",
                "This GitHub account is already linked to another SkillPulse user."
            )

        current_user.github_id = github_id
        current_user.github_access_token = encrypted_token
        current_user.github_refresh_token = encrypted_refresh_token
        current_user.github_token_expires_at = github_token_expires_at
        current_user.github_refresh_token_expires_at = github_refresh_token_expires_at
        db.commit()

        #  NEW: redirect by role
        role = current_user.role.value if current_user.role else "developer"

        return RedirectResponse(
            url=f"{_frontend_base_url()}/dashboard/{role}?github_connected=true"
        )

    # Register flow: reject if already registered

    if not db_user:
        if db.query(User).filter(User.username == username).first():
            username = f"{username}_gh"
        if db.query(User).filter(User.work_email == work_email).first():
            return _frontend_oauth_error("email_already_registered", "This email is already registered with a different SkillPulse account.")

        db_user = User(
            github_id=github_id,
            username=username,
            full_name=full_name,
            work_email=work_email,
            hashed_password="",
            role=None,
            avatar_url=avatar_url,
            github_access_token=encrypted_token,
            github_refresh_token=encrypted_refresh_token,
            github_token_expires_at=github_token_expires_at,
            github_refresh_token_expires_at=github_refresh_token_expires_at,
            is_verified=True,
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
    else:
        # Update token on every login
        db_user.github_access_token = encrypted_token
        db_user.github_refresh_token = encrypted_refresh_token
        db_user.github_token_expires_at = github_token_expires_at
        db_user.github_refresh_token_expires_at = github_refresh_token_expires_at
        db.commit()

    # 4. Create JWT tokens
    access_token = create_access_token(
        data={"sub": str(db_user.id), "role": db_user.role.value if db_user.role else None},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    raw_refresh_token, hashed_refresh_token = create_refresh_token()
    refresh_expires = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    db_refresh = RefreshToken(
        token=hashed_refresh_token,
        user_id=db_user.id,
        expires_at=refresh_expires
    )
    db.add(db_refresh)
    db.commit()

    # 5. Set HttpOnly refresh token cookie
    frontend_url = f"{_frontend_base_url()}/auth/github/callback?token={access_token}"
    redirect_response = RedirectResponse(url=frontend_url)
    redirect_response.set_cookie(
        key="refresh_token",
        value=raw_refresh_token,
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/",
    )
   
    # 6. Redirect to frontend
    return redirect_response
