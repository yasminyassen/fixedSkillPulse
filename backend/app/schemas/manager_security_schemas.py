from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ManagerSecurityRepo(BaseModel):
    id: int
    name: str | None = None
    full_name: str | None = None
    is_private: bool = False
    last_analyzed_at: datetime | None = None
    security_score: float = 0.0
    total_issues: int = 0


class SecurityRiskBreakdown(BaseModel):
    high: int = 0
    medium: int = 0
    low: int = 0
    total: int = 0


class SecurityTrendPoint(BaseModel):
    period: str
    label: str
    high: int = 0
    medium: int = 0
    low: int = 0


class CommonSecurityIssue(BaseModel):
    title: str
    severity: str
    occurrences: int
    repositories_affected: int = 0


class SecurityMemberScore(BaseModel):
    id: int
    full_name: str
    username: str
    avatar_url: str | None = None
    specialization: str | None = None
    repository_count: int = 0
    security_score: float = 0.0
    high: int = 0
    medium: int = 0
    low: int = 0


class TeamSecurityOverview(BaseModel):
    overall_score: float = 0.0
    repository_count: int = 0
    total_issues: int = 0
    team_members: int = 0
    risk_breakdown: SecurityRiskBreakdown = Field(default_factory=SecurityRiskBreakdown)
    trend: list[SecurityTrendPoint] = Field(default_factory=list)
    common_issues: list[CommonSecurityIssue] = Field(default_factory=list)
    systemic_risk_analysis: str = ""
    why_this_matters: list[str] = Field(default_factory=list)
    members: list[SecurityMemberScore] = Field(default_factory=list)


class RepositorySecuritySummary(BaseModel):
    id: int
    name: str | None = None
    full_name: str | None = None
    security_score: float = 0.0
    total_issues: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


class DetectedVulnerability(BaseModel):
    id: int
    title: str
    severity: str
    description: str | None = None
    file_path: str | None = None
    line_number: int | None = None
    cwe: str | None = None
    owasp_category: str | None = None
    contributor_id: int | None = None
    contributor_name: str | None = None


class ContributorSecurityImpact(BaseModel):
    id: int
    full_name: str
    username: str
    avatar_url: str | None = None
    specialization: str | None = None
    security_score: float = 0.0
    issue_count: int = 0
    issues_fixed: int = 0
    issues_introduced: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    net_impact: str = "Neutral"


class ContributorIssueGroup(BaseModel):
    severity: str
    issues: list[DetectedVulnerability] = Field(default_factory=list)


class RepositorySecurityDetail(BaseModel):
    repository: RepositorySecuritySummary
    release_readiness: str
    detected_vulnerabilities: list[DetectedVulnerability] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    contributor_impacts: list[ContributorSecurityImpact] = Field(default_factory=list)
    issues_by_contributor: list[ContributorIssueGroup] = Field(default_factory=list)
