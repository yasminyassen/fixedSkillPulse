from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.db.database import get_db
from app.db.models import User, Repository, AnalysisRun, SkillScore
from app.core.auth_utils import get_current_user, decrypt_github_token
from app.services.github_client import verify_repo_access

router = APIRouter(prefix="/repos", tags=["repositories"])


# ── Request Schema ────────────────────────────────────────────────────────────

# class ConnectRepoRequest(BaseModel):
#     full_name: str = Field(
#         ...,
#         pattern=r"^[a-zA-Z0-9_.\-]+/[a-zA-Z0-9_.\-]+$",
#         description="GitHub repository full name in 'owner/repo' format.",
#         examples=["octocat/Hello-World"],
#     )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _require_github_token(user: User) -> str:
    """
    Decrypt and return the user's stored GitHub token.
    Raises 403 if the user has not connected a GitHub account.
    The token is decrypted server-side and never returned to the client.
    """
    if not user.github_access_token:
        raise HTTPException(
            status_code=403,
            detail=(
                "GitHub account not linked. "
                "Please connect your GitHub account to access private repositories."
            ),
        )
    return decrypt_github_token(user.github_access_token)


def _serialize_repo(repo: Repository) -> dict:
    return {
        "id": repo.id,
        "github_repo_id": repo.github_repo_id,
        "name": repo.name,
        "full_name": repo.full_name,
        "url": repo.url,
        "is_private": bool(repo.is_private),
        "connected_at": repo.connected_at.isoformat(),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

# @router.get("/list-from-github")
# async def list_github_repos(
#     page: int = Query(default=1, ge=1, le=100, description="Page number (1-based)."),
#     current_user: User = Depends(get_current_user),
# ):
#     """
#     Retrieve GitHub repositories owned by the authenticated user.

#     Calls the GitHub API using the user's stored (encrypted) token.
#     Only the fields needed by the frontend are returned — the raw GitHub
#     token is decrypted server-side and never exposed to the client.

#     Requires the user to have signed in via GitHub OAuth so that a token
#     is available with 'repo' scope.
#     """
#     github_token = _require_github_token(current_user)
#     raw_repos = await fetch_user_repos(github_token, page=page)

#     # Whitelist specific fields — do not forward the full GitHub payload
#     return [
#         {
#             "github_repo_id": str(repo["id"]),
#             "name": repo["name"],
#             "full_name": repo["full_name"],
#             "url": repo["html_url"],
#             "is_private": repo["private"],
#             "description": repo.get("description"),
#             "language": repo.get("language"),
#             "stars": repo.get("stargazers_count", 0),
#             "updated_at": repo.get("updated_at"),
#         }
#         for repo in raw_repos
#     ]


# @router.post("/connect", status_code=201)
# async def connect_repository(
#     payload: ConnectRepoRequest,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db),
# ):
#     """
#     Connect a GitHub repository to the user's SkillPulse account.

#     Security: the repository is re-verified via the GitHub API using the
#     user's own token before being saved. This ensures:
#     - The user actually owns or can access the repository.
#     - Clients cannot spoof arbitrary repository IDs or names.
#     """
#     github_token = _require_github_token(current_user)

#     # Verify ownership/access through GitHub — trust the API, not the client
#     repo_data = await verify_repo_access(github_token, payload.full_name)

#     # Prevent the same repo from being connected twice by this user
#     already_connected = (
#         db.query(Repository)
#         .filter(
#             Repository.github_repo_id == str(repo_data["id"]),
#             Repository.owner_id == current_user.id,
#         )
#         .first()
#     )
#     if already_connected:
#         raise HTTPException(
#             status_code=409,
#             detail="This repository is already connected to your account.",
#         )

#     new_repo = Repository(
#         github_repo_id=str(repo_data["id"]),
#         name=repo_data["name"],
#         full_name=repo_data["full_name"],
#         url=repo_data["html_url"],
#         is_private=int(repo_data["private"]),
#         owner_id=current_user.id,
#     )
#     db.add(new_repo)
#     db.commit()
#     db.refresh(new_repo)

#     return _serialize_repo(new_repo)


@router.get("/connected")
def list_connected_repos(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List all repositories the current user has connected to SkillPulse.
    Returns data from the SkillPulse database, not from GitHub directly.
    """
    repos = (
        db.query(Repository)
        .join(AnalysisRun)
        .join(SkillScore, SkillScore.analysis_run_id == AnalysisRun.id)
        .filter(
            SkillScore.user_id == current_user.id,
            AnalysisRun.user_id == current_user.id,
        )
        .distinct()
    )
    return [_serialize_repo(r) for r in repos]


@router.delete("/disconnect/{repo_id}")
def disconnect_repository(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Disconnect a repository from the user's SkillPulse account.

    Security: ensure the user has at least one analysis run for this repository
    
    """
    repo = (
        db.query(Repository)
        .join(AnalysisRun)
        .join(SkillScore, SkillScore.analysis_run_id == AnalysisRun.id)
        .filter(
            Repository.id == repo_id,
            SkillScore.user_id == current_user.id,
            AnalysisRun.user_id == current_user.id,
        )
        .distinct()
        .first()
    )
    if not repo:
        raise HTTPException(
            status_code=404,
            detail="Repository not found or you do not have permission to disconnect it.",
        )

    full_name = repo.full_name
    linked_scores = (
        db.query(SkillScore)
        .join(AnalysisRun, SkillScore.analysis_run_id == AnalysisRun.id)
        .filter(
            AnalysisRun.repository_id == repo_id,
            SkillScore.user_id == current_user.id,
            AnalysisRun.user_id == current_user.id,
        )
        .all()
    )
    for score in linked_scores:
        db.delete(score)
        
    db.commit()

    return {"message": f"Repository '{full_name}' disconnected successfully."}


@router.delete("/disconnect-analysis/{analysis_id}")
def disconnect_analysis_instance(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = (
        db.query(AnalysisRun)
        .join(SkillScore, SkillScore.analysis_run_id == AnalysisRun.id)
        .filter(
            AnalysisRun.id == analysis_id,
            SkillScore.user_id == current_user.id,
            AnalysisRun.user_id == current_user.id,
        )
        .first()
    )
    if not run:
        raise HTTPException(
            status_code=404,
            detail="Analysis instance not found or you do not have permission to disconnect it.",
        )

    score = (
        db.query(SkillScore)
        .join(AnalysisRun, SkillScore.analysis_run_id == AnalysisRun.id)
        .filter(
            SkillScore.analysis_run_id == analysis_id,
            SkillScore.user_id == current_user.id,
            AnalysisRun.user_id == current_user.id,
        )
        .first()
    )
    if score:
        db.delete(score)
        db.commit()

    return {"message": f"Analysis for '{run.repository.full_name}' disconnected successfully."}
