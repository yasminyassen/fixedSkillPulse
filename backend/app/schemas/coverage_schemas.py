from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel


class AcCoverageResultResponse(BaseModel):
    id: int
    story_id: int
    task_id: Optional[int]
    ac_id: int
    status: str
    score: float
    confidence: Optional[float]
    evidence: Optional[List[Any]]
    matched_chunk_ids: Optional[List[str]]
    llm_reason: Optional[str]

    class Config:
        from_attributes = True


class StoryCoverageSummaryResponse(BaseModel):
    id: int
    story_id: int
    coverage_score: float
    status: str
    matched_symbols: Optional[List[str]]

    class Config:
        from_attributes = True


class CoverageRunResponse(BaseModel):
    id: int
    repository_id: int
    document_id: int
    analysis_run_id: Optional[int]
    status: str
    overall_coverage: Optional[float]
    error_message: Optional[str]
    created_at: Optional[datetime]
    completed_at: Optional[datetime]
    story_summaries: List[StoryCoverageSummaryResponse] = []
    ac_results: List[AcCoverageResultResponse] = []

    class Config:
        from_attributes = True


class CoverageRunSummaryResponse(BaseModel):
    id: int
    repository_id: int
    document_id: int
    status: str
    overall_coverage: Optional[float]
    created_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True
