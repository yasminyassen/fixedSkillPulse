from __future__ import annotations
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
from app.db.models import DeveloperSpecialization, TaskStatus

# ==========================================
# 1. Technical Task Schemas 
# ==========================================
class TechnicalTaskBase(BaseModel):
    description: str
    type: DeveloperSpecialization
    status: TaskStatus = TaskStatus.todo
    assigned_to: Optional[int] = None
    ac_ids: List[int] = []
    due_date: Optional[datetime] = None

class TechnicalTaskCreate(TechnicalTaskBase):
    pass

class TechnicalTaskUpdate(BaseModel):
    description: Optional[str] = None
    type: Optional[DeveloperSpecialization] = None
    status: Optional[TaskStatus] = None
    assigned_to: Optional[int] = None
    ac_ids: Optional[List[int]] = None
    due_date: Optional[datetime] = None

class TechnicalTaskResponse(TechnicalTaskBase):
    id: int
    story_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        orm_mode = True

class TaskMergeRequest(BaseModel):
    task_ids: List[int]
    new_description: str

# ==========================================
# 2. User Story Schemas
# ==========================================
class UserStoryResponse(BaseModel):
    id: int
    document_id: int
    story_code: str
    title: str
    role: str
    feature: str
    benefit: str
    description: str
    acceptance_criteria: List[Dict[str, Any]] 
    priority: str
    tags: List[str]
    technical_tasks: List[TechnicalTaskResponse] = []

    class Config:
        from_attributes = True
        orm_mode = True

class UserStoryUpdate(BaseModel):
    title: Optional[str] = None
    role: Optional[str] = None
    feature: Optional[str] = None
    benefit: Optional[str] = None
    description: Optional[str] = None
    acceptance_criteria: Optional[List[Dict[str, Any]]] = None
    priority: Optional[str] = None
    tags: Optional[List[str]] = None

class UserStoryCreate(UserStoryUpdate):
    title: str
    description: str
    acceptance_criteria: List[Dict[str, Any]] = Field(default_factory=list)
    priority: str = "medium"
    tags: List[str] = Field(default_factory=list)
    technical_tasks: List[TechnicalTaskCreate] = Field(default_factory=list)
# ==========================================
# 3. LLM AI Extraction Schemas
# ==========================================
class TechnicalTaskLLM(BaseModel):
    description: str
    type: str
    ac_ids: List[int]

class AcceptanceCriteriaLLM(BaseModel):
    id: int
    text: str

class UserStoryLLMOutput(BaseModel):
    story_code: str = Field(..., pattern=r"^US-\d{3,4}$")
    title: str = Field(..., min_length=5, max_length=200)
    role: str = Field(..., min_length=1, max_length=100)
    feature: str = Field(..., min_length=5)
    benefit: str = Field(..., min_length=5)
    description: str = Field(...)
    acceptance_criteria: List[AcceptanceCriteriaLLM] = Field(..., min_length=1)
    priority: str = Field(default="medium", pattern=r"^(critical|high|medium|low)$")
    tags: List[str] = Field(default_factory=list)
    technical_tasks: List[TechnicalTaskLLM] = Field(..., min_length=1)

    @field_validator("description")
    @classmethod
    def description_must_follow_format(cls, v: str) -> str:
        lower = v.lower()
        if not ("as a" in lower and "i want" in lower and "so that" in lower):
            raise ValueError("description must follow 'As a <role>, I want <feature>, so that <benefit>.'")
        return v

    @field_validator("tags", mode="before")
    @classmethod
    def normalise_tags(cls, v):
        if isinstance(v, list):
            return [str(t).lower().strip() for t in v]
        return []

    @field_validator("story_code", mode="before")
    @classmethod
    def uppercase_story_code(cls, v: str) -> str:
        return v.upper().strip()

class ExtractionBatchLLMOutput(BaseModel):
    user_stories: List[UserStoryLLMOutput] = Field(..., min_length=1)

# ==========================================
# 4. Document & Response Schemas
# ==========================================
class DocumentUploadResponse(BaseModel):
    document_id: int
    title: str
    file_type: str
    status: str
    message: str

class ExtractionResultResponse(BaseModel):
    document_id: int
    status: str
    stories_extracted: int
    processed_at: Optional[datetime]
    error_message: Optional[str] = None
