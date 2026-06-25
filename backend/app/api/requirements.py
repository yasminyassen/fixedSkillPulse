import os
import tempfile
from typing import List
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, Form
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import RequirementDocument, UserRole, UserStory, DocumentType, DocumentStatus, User, TechnicalTask, Repository, RepositoryContributor, TaskStatus, AnalysisRun, SkillScore, AcCoverageResult, StoryCoverageSummary, TaskEmbeddingRecord
from app.api.auth import get_current_user 
from app.schemas.prd_schemas import UserStoryResponse, ExtractionResultResponse, TechnicalTaskUpdate, TechnicalTaskCreate, TechnicalTaskResponse, UserStoryUpdate, UserStoryCreate, TaskMergeRequest
from ai_services.requirements.prd_extractor import parse_prd_to_stories
from datetime import datetime, timezone
from sqlalchemy.orm import joinedload
from app.services.github_client import fetch_repo_collaborators
from app.core.auth_utils import decrypt_github_token
from app.services.requirement_coverage_service import ensure_repository_ready_for_requirements

router = APIRouter(prefix="/requirements", tags=["Requirements & User Stories"])


def _repo_full_name(repo: Repository) -> str:
    full_name = (repo.full_name or "").strip()
    if not full_name:
        parts = (repo.url or "").rstrip("/").replace(".git", "").split("/")
        if len(parts) >= 2:
            full_name = f"{parts[-2]}/{parts[-1]}"
    if "/" not in full_name:
        raise HTTPException(status_code=400, detail="Invalid repository URL format.")
    return full_name


def _repository_owner_login(full_name: str) -> str:
    return full_name.split("/", 1)[0]


def _validate_assignment_candidate(db: Session, repo_id: int, user_id: int) -> None:
    user = (
        db.query(User)
        .filter(User.id == user_id, User.role == UserRole.developer)
        .first()
    )
    if not user:
        raise HTTPException(status_code=400, detail="Assigned user must be a registered SkillPulse developer.")

    link = (
        db.query(RepositoryContributor)
        .filter(
            RepositoryContributor.repository_id == repo_id,
            RepositoryContributor.user_id == user_id,
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=400, detail="Assigned developer must have repository access.")


def _task_repository_id(db: Session, task: TechnicalTask) -> int | None:
    return (
        db.query(RequirementDocument.repository_id)
        .join(UserStory, UserStory.document_id == RequirementDocument.id)
        .filter(UserStory.id == task.story_id)
        .scalar()
    )

@router.post("/upload", response_model=ExtractionResultResponse)
async def upload_and_extract_prd(
    file: UploadFile = File(...),
    repository_id: int = Form(None),
    repo_url: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role.value != "manager":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only managers can upload PRD documents."
        )
    if repository_id is None:
        if not repo_url:
            raise HTTPException(status_code=400, detail="A repository is required before uploading a PRD.")
        cleaned_url = repo_url.strip().rstrip("/")
        if not cleaned_url.startswith("https://github.com/"):
            raise HTTPException(status_code=400, detail="Repository URL must start with https://github.com/")
        full_name = cleaned_url.replace("https://github.com/", "").replace(".git", "")
        repo_name = full_name.split("/")[-1]
        repo = (
            db.query(Repository)
            .filter((Repository.url == cleaned_url) | (Repository.full_name == full_name))
            .first()
        )
        if not repo:
            repo = Repository(
                name=repo_name,
                full_name=full_name,
                url=cleaned_url,
                github_repo_id=None,
                is_private=False,
            )
            db.add(repo)
            db.commit()
            db.refresh(repo)
        repository_id = repo.id

    ext = os.path.splitext(file.filename)[1].lower()
    doc_type = None
    
    if ext == ".pdf": 
        doc_type = DocumentType.pdf
    elif ext in [".md", ".txt"]: 
        doc_type = DocumentType.markdown
    elif ext in [".xlsx", ".xls", ".csv"]: 
        doc_type = DocumentType.excel
    else:
        raise HTTPException(status_code=400, detail="Unsupported file format.")

    db_doc = RequirementDocument(
        uploaded_by_id=current_user.id,
        repository_id=repository_id,
        title=file.filename,
        original_filename=file.filename,
        file_type=doc_type,
        status=DocumentStatus.processing
    )
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_path = temp_file.name

        extracted_stories = await parse_prd_to_stories(temp_path)
        
        os.remove(temp_path)

        db_stories = []
        for story_data in extracted_stories:
            new_story = UserStory(
                document_id=db_doc.id,
                story_code=story_data.get("story_code", "US-XXX"),
                title=story_data.get("title", "Untitled"),
                role=story_data.get("role", "user"),
                feature=story_data.get("feature", ""),
                benefit=story_data.get("benefit", ""),
                description=story_data.get("description", ""),
                acceptance_criteria=story_data.get("acceptance_criteria", []),
                priority=story_data.get("priority", "medium").lower(),
                tags=story_data.get("tags", [])
            )
            
            tasks_data = story_data.get("technical_tasks", [])
            for task_data in tasks_data:
                new_task = TechnicalTask(
                    description=task_data.get("description", ""),
                    type=task_data.get("type", "backend"),
                    ac_ids=task_data.get("ac_ids", [])
                )
                new_story.technical_tasks.append(new_task)

            db_stories.append(new_story)
        
        db.add_all(db_stories)
        
        db_doc.status = DocumentStatus.extracted
        db_doc.processed_at = datetime.now(timezone.utc)
        
        db.commit()

        return ExtractionResultResponse(
            document_id=db_doc.id,
            status=db_doc.status,
            stories_extracted=len(db_stories),
            processed_at=db_doc.processed_at
        )

    except Exception as e:
        db_doc.status = DocumentStatus.failed
        db_doc.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{doc_id}/stories", response_model=List[UserStoryResponse])
def get_document_stories(
    doc_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stories = db.query(UserStory)\
        .options(joinedload(UserStory.technical_tasks))\
        .filter(UserStory.document_id == doc_id)\
        .all()
        
    if not stories:
        raise HTTPException(status_code=404, detail="No stories found for this document.")
    return stories

@router.patch("/tasks/{task_id}", response_model=TechnicalTaskResponse)
def update_technical_task(
    task_id: int,
    task_update: TechnicalTaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role.value != "manager":
        raise HTTPException(status_code=403, detail="Only managers can edit tasks.")

    db_task = db.query(TechnicalTask).filter(TechnicalTask.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found.")

    update_data = task_update.dict(exclude_unset=True)
    if update_data.get("assigned_to"):
        repo_id = _task_repository_id(db, db_task)
        if not repo_id:
            raise HTTPException(status_code=400, detail="Task is not linked to a repository.")
        _validate_assignment_candidate(db, repo_id, update_data["assigned_to"])

    for key, value in update_data.items():
        setattr(db_task, key, value)

    db.commit()
    db.refresh(db_task)
    return db_task

@router.post("/stories/{story_id}/tasks", response_model=TechnicalTaskResponse)
def create_manual_task(
    story_id: int,
    task_in: TechnicalTaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role.value != "manager":
        raise HTTPException(status_code=403, detail="Only managers can add tasks.")

    story = db.query(UserStory).filter(UserStory.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found.")

    if task_in.assigned_to:
        repo_id = (
            db.query(RequirementDocument.repository_id)
            .filter(RequirementDocument.id == story.document_id)
            .scalar()
        )
        if not repo_id:
            raise HTTPException(status_code=400, detail="Story is not linked to a repository.")
        _validate_assignment_candidate(db, repo_id, task_in.assigned_to)

    new_task = TechnicalTask(
        story_id=story_id,
        description=task_in.description,
        type=task_in.type,
        ac_ids=task_in.ac_ids,
        status=task_in.status,
        assigned_to=task_in.assigned_to,
        due_date=task_in.due_date
    )
    
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return new_task

@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_technical_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role.value != "manager":
        raise HTTPException(status_code=403, detail="Only managers can delete tasks.")

    db_task = db.query(TechnicalTask).filter(TechnicalTask.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found.")

    db.delete(db_task)
    db.commit()
    return

@router.post("/repositories/{repo_id}/sync-contributors")
async def sync_contributors_endpoint(
    repo_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role.value != "manager":
        raise HTTPException(status_code=403, detail="Only managers can sync repos.")

    repo = db.query(Repository).filter(Repository.id == repo_id).first()
    if not repo or not repo.url:
        raise HTTPException(status_code=404, detail="Repository not found or has no URL.")

    full_name = _repo_full_name(repo)

    manager_token = None
    if current_user.github_access_token:
        try:
            manager_token = decrypt_github_token(current_user.github_access_token)
        except Exception:
            raise HTTPException(status_code=401, detail="Failed to decrypt GitHub token.")
    collaborators_data = []
    sync_warnings: list[str] = []
    try:
        collaborators_data = await fetch_repo_collaborators(manager_token, full_name)
    except HTTPException as exc:
        (
            db.query(RepositoryContributor)
            .filter(RepositoryContributor.repository_id == repo.id)
            .delete(synchronize_session=False)
        )
        db.commit()
        raise HTTPException(status_code=exc.status_code, detail=f"Unable to verify repository access for assignment candidates: {exc.detail}")

    added_count = 0
    removed_count = 0
    access_logins = {
        item.get("login")
        for item in collaborators_data
        if item.get("login")
    }
    access_logins.add(_repository_owner_login(full_name))

    developer_users = (
        db.query(User)
        .filter(
            User.username.in_(access_logins),
            User.role == UserRole.developer,
        )
        .all()
    ) if access_logins else []

    eligible_user_ids = {user.id for user in developer_users}

    for user in developer_users:
        link_exists = db.query(RepositoryContributor).filter(
            RepositoryContributor.repository_id == repo.id,
            RepositoryContributor.user_id == user.id
        ).first()

        if not link_exists:
            new_link = RepositoryContributor(repository_id=repo.id, user_id=user.id)
            db.add(new_link)
            added_count += 1

    stale_links = (
        db.query(RepositoryContributor)
        .filter(RepositoryContributor.repository_id == repo.id)
        .all()
    )
    for link in stale_links:
        if link.user_id not in eligible_user_ids:
            db.delete(link)
            removed_count += 1
            
    db.commit()
    return {
        "message": f"Successfully refreshed {len(developer_users)} assignment candidates for this repo.",
        "added_count": added_count,
        "removed_count": removed_count,
        "matched_count": len(developer_users),
        "warnings": sync_warnings,
    }

@router.get("/repositories/{repo_id}/stories", response_model=List[UserStoryResponse])
def get_stories_by_repository(
    repo_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stories = db.query(UserStory)\
        .join(RequirementDocument, UserStory.document_id == RequirementDocument.id)\
        .options(joinedload(UserStory.technical_tasks))\
        .filter(RequirementDocument.repository_id == repo_id)\
        .all()
        
    return stories    


@router.post("/repositories/{repo_id}/stories", response_model=UserStoryResponse)
def create_manual_story(
    repo_id: int,
    story_in: UserStoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role.value != "manager":
        raise HTTPException(status_code=403, detail="Only managers can add requirements.")

    document = (
        db.query(RequirementDocument)
        .filter(
            RequirementDocument.repository_id == repo_id,
            RequirementDocument.status == DocumentStatus.confirmed,
        )
        .order_by(RequirementDocument.processed_at.desc(), RequirementDocument.id.desc())
        .first()
    )
    if not document:
        raise HTTPException(status_code=400, detail="No confirmed requirements document exists for this repository.")

    existing_count = db.query(UserStory).filter(UserStory.document_id == document.id).count()
    story_code = f"US-{existing_count + 1:03d}"
    new_story = UserStory(
        document_id=document.id,
        story_code=story_code,
        title=story_in.title,
        role=story_in.role or "user",
        feature=story_in.feature or story_in.title,
        benefit=story_in.benefit or "business value",
        description=story_in.description,
        acceptance_criteria=story_in.acceptance_criteria or [],
        priority=(story_in.priority or "medium").lower(),
        tags=story_in.tags or [],
    )

    for task_in in story_in.technical_tasks or []:
        if task_in.assigned_to:
            _validate_assignment_candidate(db, repo_id, task_in.assigned_to)
        new_story.technical_tasks.append(TechnicalTask(
            description=task_in.description,
            type=task_in.type,
            ac_ids=task_in.ac_ids,
            status=task_in.status,
            assigned_to=task_in.assigned_to,
            due_date=task_in.due_date,
        ))

    db.add(new_story)
    db.commit()
    db.refresh(new_story)
    return new_story


@router.get("/repositories/{repo_id}/developer")
def get_developer_requirements_by_repository(
    repo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role.value != "developer":
        raise HTTPException(status_code=403, detail="Only developers can view assigned requirements.")

    document = (
        db.query(RequirementDocument)
        .filter(
            RequirementDocument.repository_id == repo_id,
            RequirementDocument.status == DocumentStatus.confirmed,
        )
        .order_by(RequirementDocument.processed_at.desc())
        .first()
    )
    if not document:
        return {
            "document_id": None,
            "summary": {"assigned_stories": 0, "assigned_tasks": 0},
            "stories": [],
        }

    assigned_tasks = (
        db.query(TechnicalTask)
        .join(UserStory, TechnicalTask.story_id == UserStory.id)
        .filter(
            UserStory.document_id == document.id,
            TechnicalTask.assigned_to == current_user.id,
        )
        .order_by(TechnicalTask.id.asc())
        .all()
    )
    if not assigned_tasks:
        return {
            "document_id": document.id,
            "summary": {"assigned_stories": 0, "assigned_tasks": 0},
            "stories": [],
        }

    tasks_by_story: dict[int, list[TechnicalTask]] = {}
    visible_ac_ids_by_story: dict[int, set[int]] = {}
    for task in assigned_tasks:
        tasks_by_story.setdefault(task.story_id, []).append(task)
        visible_ac_ids_by_story.setdefault(task.story_id, set()).update(task.ac_ids or [])

    stories = (
        db.query(UserStory)
        .filter(UserStory.id.in_(tasks_by_story.keys()))
        .order_by(UserStory.id.asc())
        .all()
    )

    story_payloads = []
    for story in stories:
        visible_ac_ids = visible_ac_ids_by_story.get(story.id, set())
        visible_criteria = [
            ac
            for ac in (story.acceptance_criteria or [])
            if isinstance(ac, dict) and ac.get("id") in visible_ac_ids
        ]
        story_payloads.append({
            "story_id": story.id,
            "story_code": story.story_code,
            "title": story.title,
            "description": story.description,
            "priority": story.priority,
            "acceptance_criteria": visible_criteria,
            "tasks": [
                {
                    "task_id": task.id,
                    "story_id": task.story_id,
                    "description": task.description,
                    "type": getattr(task.type, "value", task.type),
                    "status": getattr(task.status, "value", task.status),
                    "ac_ids": task.ac_ids or [],
                    "due_date": task.due_date,
                    "assigned_to": task.assigned_to,
                }
                for task in tasks_by_story.get(story.id, [])
            ],
        })

    return {
        "document_id": document.id,
        "summary": {
            "assigned_stories": len(story_payloads),
            "assigned_tasks": len(assigned_tasks),
        },
        "stories": story_payloads,
    }


@router.post("/{doc_id}/confirm", status_code=status.HTTP_200_OK)
def confirm_requirement_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role.value != "manager":
        raise HTTPException(status_code=403, detail="Only managers can confirm requirements.")
        
    doc = db.query(RequirementDocument).filter(RequirementDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    if not doc.repository_id:
        raise HTTPException(status_code=400, detail="Requirement document is not linked to a repository.")

    doc.status = DocumentStatus.confirmed 
    db.commit()
    
    return {"message": "Requirements confirmed and published successfully."}


@router.get("/repositories/{repo_id}/analysis-readiness")
def get_repository_analysis_readiness(
    repo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        run = ensure_repository_ready_for_requirements(db, repo_id)
    except ValueError as exc:
        return {
            "ready": False,
            "reason": str(exc),
            "latest_analysis": None,
        }
    return {
        "ready": True,
        "reason": None,
        "latest_analysis": {
            "analysis_run_id": run.id,
            "status": run.status,
            "branch": run.branch,
            "commit_sha": run.commit_sha,
            "completed_at": run.completed_at,
        },
    }


@router.get("/repositories")
def list_requirement_repositories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role.value == "developer":
        query = (
            db.query(Repository)
            .join(RequirementDocument, RequirementDocument.repository_id == Repository.id)
            .join(UserStory, UserStory.document_id == RequirementDocument.id)
            .join(TechnicalTask, TechnicalTask.story_id == UserStory.id)
            .filter(
                RequirementDocument.status == DocumentStatus.confirmed,
                TechnicalTask.assigned_to == current_user.id,
            )
        )
    else:
        linked_run_ids = (
            select(SkillScore.analysis_run_id)
            .where(SkillScore.user_id == current_user.id)
        )
        query = (
            db.query(Repository)
            .join(AnalysisRun, AnalysisRun.repository_id == Repository.id)
            .filter(
                AnalysisRun.status == "completed",
                or_(
                    AnalysisRun.user_id == current_user.id,
                    AnalysisRun.id.in_(linked_run_ids),
                ),
            )
        )

    repos = query.distinct().order_by(Repository.connected_at.desc()).all()
    return [
        {
            "repo_id": repo.id,
            "repo_name": repo.name,
            "full_name": repo.full_name,
            "url": repo.url,
            "branch": "main",
            "status": "requirements",
        }
        for repo in repos
    ]


@router.get("/repositories/developer/assigned")
def list_developer_assigned_requirement_repositories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role.value != "developer":
        raise HTTPException(status_code=403, detail="Only developers can view assigned requirement repositories.")

    repos = (
        db.query(Repository)
        .join(RequirementDocument, RequirementDocument.repository_id == Repository.id)
        .join(UserStory, UserStory.document_id == RequirementDocument.id)
        .join(TechnicalTask, TechnicalTask.story_id == UserStory.id)
        .filter(
            RequirementDocument.status == DocumentStatus.confirmed,
            TechnicalTask.assigned_to == current_user.id,
        )
        .distinct()
        .order_by(Repository.connected_at.desc())
        .all()
    )
    return [
        {
            "repo_id": repo.id,
            "repo_name": repo.name,
            "full_name": repo.full_name,
            "url": repo.url,
            "branch": "main",
            "status": "assigned_requirements",
        }
        for repo in repos
    ]


@router.patch("/stories/{story_id}", response_model=UserStoryResponse)
def update_user_story(
    story_id: int,
    story_update: UserStoryUpdate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role.value != "manager":
        raise HTTPException(status_code=403, detail="Only managers can edit stories.")
        
    db_story = db.query(UserStory).filter(UserStory.id == story_id).first()
    if not db_story:
        raise HTTPException(status_code=404, detail="Story not found.")
        
    update_data = story_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_story, key, value)
        
    db.commit()
    db.refresh(db_story)
    return db_story


@router.delete("/stories/{story_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_story(
    story_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role.value != "manager":
        raise HTTPException(status_code=403, detail="Only managers can delete requirements.")

    db_story = db.query(UserStory).filter(UserStory.id == story_id).first()
    if not db_story:
        raise HTTPException(status_code=404, detail="Story not found.")

    task_ids = [task.id for task in db_story.technical_tasks]
    db.query(AcCoverageResult).filter(AcCoverageResult.story_id == story_id).delete(synchronize_session=False)
    db.query(StoryCoverageSummary).filter(StoryCoverageSummary.story_id == story_id).delete(synchronize_session=False)
    db.query(TaskEmbeddingRecord).filter(TaskEmbeddingRecord.story_id == story_id).delete(synchronize_session=False)
    if task_ids:
        db.query(AcCoverageResult).filter(AcCoverageResult.task_id.in_(task_ids)).update(
            {AcCoverageResult.task_id: None},
            synchronize_session=False,
        )

    db.delete(db_story)
    db.commit()
    return

@router.post("/stories/{story_id}/tasks/merge", response_model=TechnicalTaskResponse)
def merge_technical_tasks(
    story_id: int,
    merge_req: TaskMergeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role.value != "manager":
        raise HTTPException(status_code=403, detail="Only managers can merge tasks.")
        
    tasks_to_merge = db.query(TechnicalTask).filter(
        TechnicalTask.id.in_(merge_req.task_ids),
        TechnicalTask.story_id == story_id
    ).all()
    
    if len(tasks_to_merge) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 tasks to merge.")
        
    combined_ac_ids = set()
    for t in tasks_to_merge:
        if t.ac_ids:
            combined_ac_ids.update(t.ac_ids)
            
    task_type = tasks_to_merge[0].type

    new_task = TechnicalTask(
        story_id=story_id,
        description=merge_req.new_description,
        type=task_type,
        ac_ids=list(combined_ac_ids),
        status=TaskStatus.todo
    )
    db.add(new_task)
    for t in tasks_to_merge:
        db.delete(t)
        
    db.commit()
    db.refresh(new_task)
    return new_task

@router.get("/repositories/{repo_id}/contributors")
def get_repo_contributors(
    repo_id: int,
    specialization: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = (
        db.query(User)
        .join(RepositoryContributor, RepositoryContributor.user_id == User.id)
        .filter(
                RepositoryContributor.repository_id == repo_id,
                User.role == UserRole.developer)
    )
    if specialization in {"backend", "frontend", "qa"}:
        query = query.filter(User.specialization == specialization)
    contributors = query.order_by(User.full_name.asc()).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "full_name": u.full_name,
            "email": u.work_email,
            "specialization": u.specialization.value if u.specialization else None,
        }
        for u in contributors
    ]
