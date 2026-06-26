from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float, JSON, Enum, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base
from datetime import datetime, timedelta
from sqlalchemy.dialects import postgresql
import enum

# Roles
class UserRole(str, enum.Enum):
    developer = "developer"
    manager = "manager"
    recruiter = "recruiter"

class DeveloperSpecialization(str, enum.Enum):
    backend = "backend"
    frontend = "frontend"
    qa = "qa"
class TaskStatus(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    github_id = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False) 
    full_name = Column(String, nullable=False) 
    work_email = Column(String, unique=True, index=True, nullable=False) 
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(UserRole), nullable=True, default=None)
    specialization = Column(Enum(DeveloperSpecialization), nullable=True, default=None)
    avatar_url = Column(String, nullable=True)
    github_access_token = Column(String, nullable=True)
    github_refresh_token = Column(String, nullable=True)
    github_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    github_refresh_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    organization = Column(String, nullable=True)
    job_title    = Column(String, nullable=True)
    is_verified = Column(Boolean, nullable=False, default=False)
    verification_code = Column(String, nullable=True)
    reset_password_token = Column(String, nullable=True)
    reset_password_expires_at = Column(DateTime(timezone=True), nullable=True)
    
    department              = Column(String,  nullable=True)
    hiring_focus            = Column(String,  nullable=True)

    security_score_visible  = Column(Boolean, nullable=True, default=True)
    high_priority_threshold = Column(Integer, nullable=True, default=75)
    weight_code_quality     = Column(Integer, nullable=True, default=20)
    weight_architecture     = Column(Integer, nullable=True, default=20)
    weight_maintainability  = Column(Integer, nullable=True, default=20)
    weight_security         = Column(Integer, nullable=True, default=20)
    weight_git_activity     = Column(Integer, nullable=True, default=20)
    weight_requirements     = Column(Integer, nullable=True, default=10)
    global_team_insights    = Column(JSON, nullable=True)
   
    
    analysis_runs = relationship("AnalysisRun", back_populates="user", cascade="all, delete-orphan")
    recruiter_tasks = relationship("RecruiterTask", back_populates="recruiter", cascade="all, delete-orphan")
    contributor_analysis_summaries = relationship("ContributorAnalysisSummary", back_populates="user", cascade="all, delete-orphan")

class Repository(Base):
    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, index=True)
    github_repo_id = Column(String, unique=True, index=True)
    name = Column(String)
    full_name = Column(String)
    url = Column(String)
    is_private = Column(Boolean, default=False)
    connected_at = Column(DateTime(timezone=True), server_default=func.now())
    
    analysis_runs = relationship("AnalysisRun", back_populates="repository")
    repository_analyses = relationship("RepositoryAnalysis", back_populates="repository")
    contributor_analysis_summaries = relationship("ContributorAnalysisSummary", back_populates="repository", cascade="all, delete-orphan")

class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    branch = Column(String, default="main")
    commit_sha = Column(String, nullable=True)   
    analysis_scope = Column(String, default="repository")
    contributor_login = Column(String, nullable=True)
    status = Column(String, default="pending")
    triggered_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    repository = relationship("Repository", back_populates="analysis_runs")
    code_metrics = relationship("CodeMetrics", back_populates="analysis_run", cascade="all, delete-orphan")
    security_findings = relationship("SecurityFinding", back_populates="analysis_run", cascade="all, delete-orphan")
    skill_scores = relationship("SkillScore", back_populates="analysis_run", cascade="all, delete-orphan")
    sonar_summary = relationship("SonarAnalysisSummary", back_populates="analysis_run", cascade="all, delete-orphan", uselist=False)
    sonar_file_measures = relationship("SonarFileMeasure", back_populates="analysis_run", cascade="all, delete-orphan")
    sonar_issues = relationship("SonarIssue", back_populates="analysis_run", cascade="all, delete-orphan")
    contributor_analysis_summaries = relationship("ContributorAnalysisSummary", back_populates="analysis_run", cascade="all, delete-orphan")
    user = relationship("User", back_populates="analysis_runs")
    ai_insights = Column(JSON, nullable=True)
    recruiter_candidate = relationship("RecruiterCandidate", back_populates="analysis_run", uselist=False)


class RepositoryAnalysis(Base):
    __tablename__ = "repository_analyses"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    latest_commit_sha = Column(String, nullable=True)
    analysis_version = Column(String, nullable=False)
    analyzed_at = Column(DateTime(timezone=True), nullable=True)
    analysis_status = Column(String, nullable=False, default="pending")
    results_path = Column(String, nullable=True)
    force_reanalyzed = Column(Boolean, default=False)
    last_run_id = Column(Integer, ForeignKey("analysis_runs.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    repository = relationship("Repository", back_populates="repository_analyses")
    user = relationship("User")
    last_run = relationship("AnalysisRun")


class RecruiterTask(Base):
    __tablename__ = "recruiter_tasks"

    id = Column(Integer, primary_key=True, index=True)
    recruiter_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    csv_filename = Column(String, nullable=True)
    total_candidates = Column(Integer, nullable=False, default=0)
    valid_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    recruiter = relationship("User", back_populates="recruiter_tasks")
    candidates = relationship("RecruiterCandidate", back_populates="task")


class RecruiterCandidate(Base):
    __tablename__ = "recruiter_candidates"

    id = Column(Integer, primary_key=True, index=True)
    analysis_run_id = Column(Integer, ForeignKey("analysis_runs.id"), unique=True, nullable=False)
    task_id = Column(Integer, ForeignKey("recruiter_tasks.id"), nullable=True, index=True)
    candidate_name = Column(String, nullable=False)
    github_login = Column(String, nullable=True)
    github_avatar_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    analysis_run = relationship("AnalysisRun", back_populates="recruiter_candidate")
    task = relationship("RecruiterTask", back_populates="candidates")
class CodeMetrics(Base):
    __tablename__ = "code_metrics"

    id = Column(Integer, primary_key=True, index=True)
    analysis_run_id = Column(Integer, ForeignKey("analysis_runs.id"))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    file_path = Column(String)
    cyclomatic_complexity = Column(Float, nullable=True)
    lines_of_code = Column(Integer, nullable=True)
    duplication_score = Column(Float, nullable=True)
    maintainability_index = Column(Float, nullable=True)
    raw_metrics = Column(JSON, nullable=True)

    analysis_run = relationship("AnalysisRun", back_populates="code_metrics")
    user = relationship("User")

class SonarAnalysisSummary(Base):
    __tablename__ = "sonar_analysis_summaries"

    id = Column(Integer, primary_key=True, index=True)
    analysis_run_id = Column(Integer, ForeignKey("analysis_runs.id"), unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    project_key = Column(String, nullable=True)
    quality_gate = Column(String, nullable=True)
    sonar_health_score = Column(Float, nullable=True)
    measures = Column(JSON, nullable=True)
    coverage = Column(JSON, nullable=True)
    scanner = Column(JSON, nullable=True)
    ce_task = Column(JSON, nullable=True)
    raw_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    analysis_run = relationship("AnalysisRun", back_populates="sonar_summary")
    user = relationship("User")

class ContributorAnalysisSummary(Base):
    __tablename__ = "contributor_analysis_summaries"

    id = Column(Integer, primary_key=True, index=True)
    analysis_run_id = Column(Integer, ForeignKey("analysis_runs.id"), nullable=False, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    contributor_login = Column(String, nullable=True)
    files_count = Column(Integer, nullable=False, default=0)
    touched_files = Column(JSON, nullable=True)

    skill_score = Column(Float, nullable=True)
    sonar_health_score = Column(Float, nullable=True)
    security_score = Column(Float, nullable=True)

    coverage = Column(Float, nullable=True)
    bugs = Column(Integer, nullable=True)
    code_smells = Column(Integer, nullable=True)
    duplicated_lines = Column(Float, nullable=True)
    duplicated_lines_density = Column(Float, nullable=True)
    complexity = Column(Float, nullable=True)
    cognitive_complexity = Column(Float, nullable=True)
    ncloc = Column(Float, nullable=True)

    quality_gate = Column(String, nullable=True)
    measures = Column(JSON, nullable=True)
    raw_payload = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    analysis_run = relationship("AnalysisRun", back_populates="contributor_analysis_summaries")
    repository = relationship("Repository", back_populates="contributor_analysis_summaries")
    user = relationship("User", back_populates="contributor_analysis_summaries")

    __table_args__ = (
        UniqueConstraint("analysis_run_id", "user_id", name="uq_contributor_analysis_summary_run_user"),
    )

class SonarFileMeasure(Base):
    __tablename__ = "sonar_file_measures"

    id = Column(Integer, primary_key=True, index=True)
    analysis_run_id = Column(Integer, ForeignKey("analysis_runs.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    file_path = Column(String, nullable=False)
    measures = Column(JSON, nullable=True)
    coverage = Column(Float, nullable=True)
    duplicated_lines = Column(Float, nullable=True)
    duplicated_lines_density = Column(Float, nullable=True)
    ncloc = Column(Float, nullable=True)
    complexity = Column(Float, nullable=True)
    cognitive_complexity = Column(Float, nullable=True)
    functions = Column(Float, nullable=True)
    classes = Column(Float, nullable=True)
    statements = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    analysis_run = relationship("AnalysisRun", back_populates="sonar_file_measures")
    user = relationship("User")

class SonarIssue(Base):
    __tablename__ = "sonar_issues"

    id = Column(Integer, primary_key=True, index=True)
    analysis_run_id = Column(Integer, ForeignKey("analysis_runs.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    issue_key = Column(String, nullable=True)
    file_path = Column(String, nullable=True)
    line = Column(Integer, nullable=True)
    type = Column(String, nullable=True)
    severity = Column(String, nullable=True)
    rule = Column(String, nullable=True)
    message = Column(Text, nullable=True)
    status = Column(String, nullable=True)
    raw_issue = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    analysis_run = relationship("AnalysisRun", back_populates="sonar_issues")
    user = relationship("User")

class SecurityFinding(Base):
    __tablename__ = "security_findings"

    id = Column(Integer, primary_key=True, index=True)
    analysis_run_id = Column(Integer, ForeignKey("analysis_runs.id"))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    tool = Column(String)
    rule = Column(String)
    cwe = Column(String)
    file_path = Column(String)
    severity = Column(String)
    description = Column(Text)
    line_number = Column(Integer, nullable=True)
    owasp_category = Column(String)

    analysis_run = relationship("AnalysisRun", back_populates="security_findings")
    user = relationship("User")

class SkillScore(Base):
    __tablename__ = "skill_scores"

    id = Column(Integer, primary_key=True, index=True)
    analysis_run_id = Column(Integer, ForeignKey("analysis_runs.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    code_quality_score = Column(Float)
    maintainability_score = Column(Float)
    architecture_score = Column(Float, nullable=True)
    security_awareness_score = Column(Float)
    problem_solving_score = Column(Float)
    overall_score = Column(Float)
    sonar_health_score = Column(Float, nullable=True)
    

    analysis_run = relationship("AnalysisRun", back_populates="skill_scores")
    user = relationship("User")

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    token = Column(String, unique=True, index=True)  
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class DocumentType(str, enum.Enum):
    pdf = "pdf"
    markdown = "markdown"
    excel = "excel"


class DocumentStatus(str, enum.Enum):
    processing = "processing"
    extracted = "extracted"
    confirmed = "confirmed"
    failed = "failed"


class CoverageRunStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class AcCoverageStatus(str, enum.Enum):
    covered = "COVERED"
    partially_covered = "PARTIALLY_COVERED"
    not_covered = "NOT_COVERED"


def _enum_values(enum_cls):
    return [member.value for member in enum_cls]


class StoryCoverageStatus(str, enum.Enum):
    implemented = "implemented"
    partially_implemented = "partially_implemented"
    not_implemented = "not_implemented"


class StoryPriority(str, enum.Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class AssignmentStatus(str, enum.Enum):
    assigned = "assigned"
    in_progress = "in_progress"
    completed = "completed"
    blocked = "blocked"


class RequirementDocument(Base):
    __tablename__ = "requirement_documents"

    id = Column(Integer, primary_key=True, index=True)
    uploaded_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    repository_id = Column(Integer, ForeignKey("repositories.id"), nullable=True)
    title = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_type = Column(Enum(DocumentType), nullable=False)
    status = Column(Enum(DocumentStatus), default=DocumentStatus.processing, nullable=False)
    error_message = Column(Text, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)

    uploader = relationship("User", foreign_keys=[uploaded_by_id], backref="uploaded_documents")
    repository = relationship("Repository", foreign_keys=[repository_id], backref="requirement_documents")
    user_stories = relationship("UserStory", back_populates="document", cascade="all, delete-orphan")




class UserStory(Base):
    __tablename__ = "user_stories"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("requirement_documents.id", ondelete="CASCADE"), nullable=False)
    story_code = Column(String, nullable=False)
    title = Column(String, nullable=False)
    role = Column(String, nullable=False)
    feature = Column(String, nullable=False)
    benefit = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    acceptance_criteria = Column(JSON, nullable=False, default=[])
    priority = Column(String, nullable=False, default="medium")
    tags = Column(JSON, nullable=False, default=[])
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    technical_tasks = relationship("TechnicalTask", back_populates="story", cascade="all, delete-orphan")
    document = relationship("RequirementDocument", back_populates="user_stories")


class TechnicalTask(Base):
    __tablename__ = "technical_tasks"

    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("user_stories.id", ondelete="CASCADE"), nullable=False)
    description = Column(Text, nullable=False)
    type = Column(postgresql.ENUM('backend', 'frontend', 'qa', name='developerspecialization', create_type=False), nullable=False)
    status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.todo)
    assigned_to = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    ac_ids = Column(JSON, nullable=True, default=[])
    
    due_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    story = relationship("UserStory", back_populates="technical_tasks")

class RepositoryContributor(Base):
    __tablename__ = "repository_contributors"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    repository = relationship("Repository")
    user = relationship("User")


class RequirementCoverageRun(Base):
    __tablename__ = "requirement_coverage_runs"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(Integer, ForeignKey("requirement_documents.id", ondelete="CASCADE"), nullable=False)
    analysis_run_id = Column(Integer, ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True)
    status = Column(Enum(CoverageRunStatus), default=CoverageRunStatus.pending, nullable=False)
    overall_coverage = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    discovery_links = Column(JSON, nullable=True)
    developer_task_results = Column(JSON, nullable=True)
    branch = Column(String, nullable=True)
    commit_sha = Column(String, nullable=True)
    requirements_snapshot_hash = Column(String, nullable=True)
    tasks_snapshot_hash = Column(String, nullable=True)
    assignments_snapshot_hash = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    repository = relationship("Repository")
    document = relationship("RequirementDocument")
    ac_results = relationship("AcCoverageResult", back_populates="coverage_run", cascade="all, delete-orphan")
    story_summaries = relationship("StoryCoverageSummary", back_populates="coverage_run", cascade="all, delete-orphan")
    code_embeddings = relationship("CodeEmbeddingRecord", back_populates="coverage_run", cascade="all, delete-orphan")
    task_embeddings = relationship("TaskEmbeddingRecord", back_populates="coverage_run", cascade="all, delete-orphan")


class CodeEmbeddingRecord(Base):
    __tablename__ = "code_embedding_records"

    id = Column(Integer, primary_key=True, index=True)
    coverage_run_id = Column(Integer, ForeignKey("requirement_coverage_runs.id", ondelete="CASCADE"), nullable=False)
    faiss_id = Column(Integer, nullable=False)
    file_path = Column(String, nullable=False)
    symbol_name = Column(String, nullable=True)
    symbol_type = Column(String, nullable=True)
    chunk_id = Column(String, nullable=False)
    start_line = Column(Integer, nullable=True)
    end_line = Column(Integer, nullable=True)
    chunk_text = Column(Text, nullable=False)
    language = Column(String, nullable=False)

    coverage_run = relationship("RequirementCoverageRun", back_populates="code_embeddings")


class TaskEmbeddingRecord(Base):
    __tablename__ = "task_embedding_records"

    id = Column(Integer, primary_key=True, index=True)
    coverage_run_id = Column(Integer, ForeignKey("requirement_coverage_runs.id", ondelete="CASCADE"), nullable=False)
    faiss_id = Column(Integer, nullable=False)
    task_id = Column(Integer, ForeignKey("technical_tasks.id", ondelete="CASCADE"), nullable=False)
    story_id = Column(Integer, ForeignKey("user_stories.id", ondelete="CASCADE"), nullable=False)
    embedding_text = Column(Text, nullable=False)

    coverage_run = relationship("RequirementCoverageRun", back_populates="task_embeddings")


class AcCoverageResult(Base):
    __tablename__ = "ac_coverage_results"

    id = Column(Integer, primary_key=True, index=True)
    coverage_run_id = Column(Integer, ForeignKey("requirement_coverage_runs.id", ondelete="CASCADE"), nullable=False)
    story_id = Column(Integer, ForeignKey("user_stories.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(Integer, ForeignKey("technical_tasks.id", ondelete="SET NULL"), nullable=True)
    ac_id = Column(Integer, nullable=False)
    status = Column(Enum(AcCoverageStatus, values_callable=_enum_values), nullable=False)
    score = Column(Float, nullable=False)
    confidence = Column(Float, nullable=True)
    evidence = Column(JSON, nullable=True)
    matched_chunk_ids = Column(JSON, nullable=True)
    llm_reason = Column(Text, nullable=True)

    coverage_run = relationship("RequirementCoverageRun", back_populates="ac_results")


class StoryCoverageSummary(Base):
    __tablename__ = "story_coverage_summaries"

    id = Column(Integer, primary_key=True, index=True)
    coverage_run_id = Column(Integer, ForeignKey("requirement_coverage_runs.id", ondelete="CASCADE"), nullable=False)
    story_id = Column(Integer, ForeignKey("user_stories.id", ondelete="CASCADE"), nullable=False)
    coverage_score = Column(Float, nullable=False)
    status = Column(Enum(StoryCoverageStatus), nullable=False)
    matched_symbols = Column(JSON, nullable=True)

    coverage_run = relationship("RequirementCoverageRun", back_populates="story_summaries")


class ProfileActivityLog(Base):
    __tablename__ = "profile_activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    manager_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    member_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    activity_type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    manager = relationship("User", foreign_keys=[manager_id])
    actor = relationship("User", foreign_keys=[actor_id])
    member = relationship("User", foreign_keys=[member_id])
