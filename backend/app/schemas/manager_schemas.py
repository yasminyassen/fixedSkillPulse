from datetime import datetime

from pydantic import BaseModel, Field


class ManagerDashboardRepo(BaseModel):
    id: int
    name: str | None = None
    full_name: str | None = None
    is_private: bool = False
    last_analyzed_at: datetime | None = None
    analysis_count: int = 0
    member_count: int = 0


class ManagerTopPerformer(BaseModel):
    id: int
    full_name: str
    username: str
    skill_score: float | None = None
    skill_score_level: str = "Unavailable"
    sonar_health_score: float | None = None


class ManagerKpis(BaseModel):
    team_skill_score: float | None = None
    team_skill_score_level: str = "Unavailable"
    team_sonar_health_score: float | None = None
    team_size: int
    top_performer: ManagerTopPerformer | None = None
    growth_rate: float | None = None


class ManagerTrendPoint(BaseModel):
    period: str
    label: str
    skill_score: float | None = None
    skill_score_level: str = "Unavailable"
    sonar_health_score: float | None = None
    bugs: float | int | None = None
    code_smells: float | int | None = None
    coverage: float | int | None = None
    duplication_percentage: float | int | None = None
    cognitive_complexity: float | int | None = None
    quality_gate_pass_rate: float | None = None


class ManagerSkillDistribution(BaseModel):
    skill_score: float | None = None
    skill_score_level: str = "Unavailable"
    sonar_health_score: float | None = None
    bugs: float | int | None = None
    code_smells: float | int | None = None
    coverage: float | int | None = None
    duplication_percentage: float | int | None = None
    cognitive_complexity: float | int | None = None
    quality_gate_pass_rate: float | None = None


class ManagerTeamMember(BaseModel):
    id: int
    full_name: str
    username: str
    email: str
    avatar_url: str | None = None
    specialization: str | None = None
    skill_score: float | None = None
    skill_score_level: str = "Unavailable"
    sonar_health_score: float | None = None
    quality_gate: str | None = None
    bugs: float | int | None = None
    code_smells: float | int | None = None
    coverage: float | int | None = None
    duplication_percentage: float | int | None = None
    cognitive_complexity: float | int | None = None
    repository_count: int
    analysis_count: int
    sonar_delta: float | None = None


class ManagerActionableRecommendations(BaseModel):
    mandatory: list[str] = Field(default_factory=list)
    highly_required: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    enhanced: list[str] = Field(default_factory=list)


class ManagerTeamInsights(BaseModel):
    actionable_recommendations: ManagerActionableRecommendations = Field(
        default_factory=ManagerActionableRecommendations
    )


class ManagerMemberDetail(BaseModel):
    member: ManagerTeamMember
    timeline: list[ManagerTrendPoint] = Field(default_factory=list)
    key_strengths: list[str] = Field(default_factory=list)
    areas_for_improvement: list[str] = Field(default_factory=list)


class ManagerDashboardRepositorySummary(BaseModel):
    analysis_run_id: int | None = None
    repository_id: int | None = None
    repository_name: str | None = None
    organization: str | None = None
    branch: str | None = None
    last_analysis: datetime | None = None
    analyzed_on: datetime | None = None
    overall_repository_score: float | None = None
    repository_status: str = "Unavailable"


class ManagerDashboardMetricCard(BaseModel):
    key: str
    label: str
    value: float | int | str | None = None
    unit: str | None = None
    status: str | None = None


class ManagerDashboardContributorHighlight(BaseModel):
    id: int | None = None
    full_name: str | None = None
    username: str | None = None
    score: float | None = None
    reasoning: str | None = None


class ManagerDashboardTeamPerformance(BaseModel):
    average_team_score: float | None = None
    average_team_security_score: float | None = None
    average_coverage: float | None = None
    average_code_smells: float | None = None
    best_contributor: ManagerDashboardContributorHighlight | None = None
    needs_support_contributor: ManagerDashboardContributorHighlight | None = None
    total_contributors: int = 0


class ManagerDashboardContributorRow(BaseModel):
    id: int
    developer: str
    username: str
    role: str | None = None
    skill_score: float | None = None
    health_score: float | None = None
    security_score: float | None = None
    coverage: float | None = None
    bugs: float | int | None = None
    code_smells: float | int | None = None
    complexity: float | int | None = None
    status: str = "Unavailable"


class ManagerDashboardOverviewTrendPoint(BaseModel):
    period: str
    label: str
    health_score: float | None = None
    security_score: float | None = None


class ManagerDashboardRiskItem(BaseModel):
    title: str
    detail: str | None = None
    file_path: str | None = None
    metric: float | int | str | None = None
    severity: str | None = None
    count: int | None = None


class ManagerDashboardRiskGroups(BaseModel):
    high_code_smells: list[ManagerDashboardRiskItem] = Field(default_factory=list)
    high_bug_files: list[ManagerDashboardRiskItem] = Field(default_factory=list)
    files_for_bugs: list[ManagerDashboardRiskItem] = Field(default_factory=list)


class ManagerDashboardRecommendations(BaseModel):
    fix_first: list[str] = Field(default_factory=list)
    prioritize_next: list[str] = Field(default_factory=list)
    plan_when_possible: list[str] = Field(default_factory=list)
    strengthen_further: list[str] = Field(default_factory=list)
    actionable_recommendations: list[str] = Field(default_factory=list)
    prioritized_team_next_moves: list[str] = Field(default_factory=list)
    team_improvement_guidance: list[str] = Field(default_factory=list)
    best_contributor_reasoning: str | None = None
    needs_support_reasoning: str | None = None
    architectural_concerns: list[str] = Field(default_factory=list)
    delivery_risks: list[str] = Field(default_factory=list)
    quality_concerns: list[str] = Field(default_factory=list)
    team_strengths: list[str] = Field(default_factory=list)
    recommended_priorities: list[str] = Field(default_factory=list)


class ManagerDashboardOverview(BaseModel):
    repositories: list[ManagerDashboardRepo] = Field(default_factory=list)
    repository_summary: ManagerDashboardRepositorySummary = Field(default_factory=ManagerDashboardRepositorySummary)
    repository_metrics: list[ManagerDashboardMetricCard] = Field(default_factory=list)
    team_performance: ManagerDashboardTeamPerformance = Field(default_factory=ManagerDashboardTeamPerformance)
    contributors: list[ManagerDashboardContributorRow] = Field(default_factory=list)
    trends: list[ManagerDashboardOverviewTrendPoint] = Field(default_factory=list)
    risks: ManagerDashboardRiskGroups = Field(default_factory=ManagerDashboardRiskGroups)
    recommendations: ManagerDashboardRecommendations = Field(default_factory=ManagerDashboardRecommendations)
