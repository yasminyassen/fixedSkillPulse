import sys
import os
import re
import logging
import shutil
import tempfile
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fastapi import Request, APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from typing import Optional
from pydantic import BaseModel

from sqlalchemy import func, or_, select


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from app.db.database import get_db
from app.db.models import (
    Repository,
    AnalysisRun,
    SecurityFinding,
    CodeMetrics,
    SkillScore,
    SonarAnalysisSummary,
    SonarFileMeasure,
    SonarIssue,
    User,
    UserRole,
    RecruiterCandidate,
    RecruiterTask,
    RepositoryAnalysis,
    RepositoryContributor,
)
from app.core.auth_utils import get_current_user, decrypt_github_token, require_role
from app.core.rate_limiter import limiter

from app.services.github_client import (
    verify_repo_access,
    refresh_github_access_token_for_user,
    get_branch_head_sha,
    get_files_fingerprint,
    fetch_user_repo_contribution_summary,
)
from app.services.analysis_orchestrator import (
    background_analysis_task,
    background_manager_contributor_analysis_task,
    background_manager_repository_analysis_task,
    resolve_github_identity,
    build_personal_repo_context,
    run_background_analysis_task,
)
from app.services.code_analysis_service import (
    safe_float,
    safe_int,
    score_belongs_to_user,
    link_existing_run_to_user,
    build_github_connect_payload,
)
from app.services.security_service import (
    normalize_severity,
    compute_security_score_breakdown,
    group_findings_by_severity_and_file,
)
from app.services.learning_recommendations import build_learning_recommendations
from app.services.llm_client import (
    _fallback_recruiter_candidate_insights,
    generate_recruiter_candidate_insights,
)
from app.services.sonarqube_score_service import (
    build_skill_score_fields,
    build_sonar_dashboard_payload,
    build_sonar_repo_summary,
    compute_sonar_health_score,
    get_coverage_metadata,
    get_sonar_measure_map,
    get_sonar_payload,
    get_sonar_quality_gate_status,
)


router = APIRouter(prefix="/analysis", tags=["analysis"])
logger = logging.getLogger(__name__)


class RepoRequest(BaseModel):
    repo_url: str
    branch: str = "main"
    programming_language: str = "python"


class RecruiterCandidateRow(BaseModel):
    candidate_name: str
    github_login: str
    github_avatar_url: str | None = None
    repo_name: str | None = None
    repo_url: str | None = None
    task_id: int | None = None
    task_title: str | None = None
    skill_score: float | int | None = None
    skill_score_level: str = "Unavailable"
    sonar_health_score: float | None = None
    sonar_state: str = "sonar_unavailable"
    quality_gate: str | None = None
    bugs: float | int | None = None
    code_smells: float | int | None = None
    coverage: float | int | None = None
    duplication_percentage: float | int | None = None
    cognitive_complexity: float | int | None = None
    reliability_rating: str | None = None
    maintainability_rating: str | None = None
    technical_debt_minutes: float | int | None = None
    lines_of_code: float | int | None = None
    security: float
    repo_count: int
    contribution_count: int
    run_id: int
    analysis_status: str | None = None
    completed_at: datetime | None = None


class RecruiterTaskResponse(BaseModel):
    id: int
    title: str
    csv_filename: str | None = None
    total_candidates: int
    valid_count: int
    skipped_count: int
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    analyzed_count: int
    average_skill_score: float | None = None


class RecruiterCandidateDashboardRow(BaseModel):
    candidate_name: str
    github_login: str
    github_avatar_url: str | None = None
    repo_name: str
    repo_url: str | None = None
    task_id: int | None = None
    task_title: str | None = None
    skill_score: float | int | None = None
    skill_score_level: str = "Unavailable"
    sonar_health_score: float | int | None = None
    sonar_state: str = "sonar_unavailable"
    security: float | int | None = None
    quality_gate: str | None = None
    bugs: float | int | None = None
    code_smells: float | int | None = None
    coverage: float | int | None = None
    duplication_percentage: float | int | None = None
    cognitive_complexity: float | int | None = None
    reliability_rating: str | None = None
    maintainability_rating: str | None = None
    technical_debt_minutes: float | int | None = None
    lines_of_code: float | int | None = None
    repo_count: int
    contribution_count: int
    run_id: int
    analysis_status: str
    completed_at: datetime | None = None


class DashboardOverview(BaseModel):
    total_candidates: int
    average_skill_score: float | None = None
    average_sonar_health: float | None = None
    average_security_score: float | None = None
    passed_quality_gate_percentage: float | int
    high_priority_candidates: int


class TaskDistribution(BaseModel):
    excellent: int
    good: int
    fair: int
    poor: int


class RiskHeatmapRow(BaseModel):
    candidate_name: str
    code_quality: str
    security: str
    maintainability: str
    testing: str
    reliability: str


class RecruiterCandidateInsightResponse(BaseModel):
    candidate_name: str
    github_login: str
    github_avatar_url: str | None = None
    run_id: int
    repo_name: str
    task_title: str | None = None
    skill_score: float | int | None = None
    sonar_health_score: float | int | None = None
    security: float | int | None = None
    coverage: float | int | None = None
    bugs: float | int | None = None
    summary: str
    strengths: list[str]
    areas_to_improve: list[str]
    recommendation: str
    recommendation_reason: str | None = None
    risk_level: str
    generated_by: str
    generated_at: datetime | str | None = None


class RecruiterDashboardSummaryResponse(BaseModel):
    overview: DashboardOverview
    task_distribution: TaskDistribution
    risk_heatmap: list[RiskHeatmapRow]
    top_candidate: RecruiterCandidateInsightResponse | None = None


LEARNING_RECOMMENDATION_KEYS = {
    "skill",
    "why_needed",
    "priority",
    "learning_objectives",
    "estimated_effort",
    "expected_improvement",
    "resources",
}
LEARNING_RESPONSE_KEYS = {
    "analysis_run_id",
    "repo",
    "branch",
    "recommendations",
    "generated_at",
    "rag_metadata",
}


def _is_current_learning_recommendations(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    if set(payload.keys()) != LEARNING_RESPONSE_KEYS:
        return False
    if not isinstance(payload.get("analysis_run_id"), int):
        return False
    if not isinstance(payload.get("repo"), str) or not isinstance(payload.get("branch"), str):
        return False
    if not isinstance(payload.get("generated_at"), str):
        return False

    metadata = payload.get("rag_metadata")
    if not isinstance(metadata, dict):
        return False
    if not isinstance(metadata.get("enabled"), bool):
        return False
    if not isinstance(metadata.get("retrieved_count"), int):
        return False
    if not isinstance(metadata.get("retriever"), str):
        return False

    recommendations = payload.get("recommendations")
    if not isinstance(recommendations, list):
        return False
    for item in recommendations:
        if not isinstance(item, dict):
            return False
        if set(item.keys()) != LEARNING_RECOMMENDATION_KEYS:
            return False
        if str(item.get("priority")) not in {"High", "Medium", "Low"}:
            return False
        if not isinstance(item.get("learning_objectives"), list):
            return False
        resources = item.get("resources")
        if not isinstance(resources, list):
            return False
        for resource in resources:
            if not isinstance(resource, dict):
                return False
            if not {"title", "type", "provider", "url", "reason"}.issubset(resource.keys()):
                return False
    return True


def _sonar_metrics_for_learning(
    run: AnalysisRun,
    summary_row: SonarAnalysisSummary | None,
    file_measure_rows: list[SonarFileMeasure],
) -> dict:
    summary = build_sonar_repo_summary(run)
    measures = {}
    if summary_row is not None and isinstance(summary_row.measures, dict):
        measures = dict(summary_row.measures)

    file_metrics = []
    for row in file_measure_rows or []:
        file_metrics.append({
            "file_path": row.file_path,
            "coverage": row.coverage,
            "duplicated_lines": row.duplicated_lines,
            "duplicated_lines_density": row.duplicated_lines_density,
            "ncloc": row.ncloc,
            "complexity": row.complexity,
            "cognitive_complexity": row.cognitive_complexity,
            "functions": row.functions,
            "classes": row.classes,
            "statements": row.statements,
        })

    def _file_risk(item: dict) -> float:
        return float(item.get("cognitive_complexity") or 0) + float(item.get("complexity") or 0) + float(item.get("duplicated_lines_density") or 0)

    return {
        **measures,
        **summary,
        "sonar_summary_available": summary_row is not None,
        "sonar_file_metrics": sorted(file_metrics, key=_file_risk, reverse=True)[:20],
    }


def _empty_learning_recommendations_response(run: AnalysisRun, retriever: str = "keyword_fallback") -> dict:
    repo = getattr(run, "repository", None)
    return {
        "analysis_run_id": int(run.id),
        "repo": str(getattr(repo, "full_name", None) or getattr(repo, "name", None) or f"repository:{run.repository_id}"),
        "branch": str(run.branch or "main"),
        "recommendations": [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rag_metadata": {
            "enabled": retriever == "faiss",
            "retrieved_count": 0,
            "retriever": retriever if retriever in {"faiss", "keyword_fallback"} else "keyword_fallback",
        },
    }


MIN_AWARE_DATETIME = datetime.min.replace(tzinfo=timezone.utc)


def _run_sort_time(run: AnalysisRun) -> datetime:
    value = run.completed_at or run.triggered_at or MIN_AWARE_DATETIME
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _analysis_has_sonar_dashboard(run: AnalysisRun) -> bool:
    ai_insights = run.ai_insights or {}
    if not isinstance(ai_insights, dict):
        return False
    sonar_payload = ai_insights.get("sonar")
    return isinstance(sonar_payload, dict) and bool(sonar_payload) and not bool(sonar_payload.get("error"))


def _safe_number(value):
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
    else:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
    return int(numeric) if numeric.is_integer() else numeric


def _avg_present(values: list[object]) -> float | None:
    numbers = [
        float(value)
        for value in (_safe_number(item) for item in values)
        if value is not None
    ]
    if not numbers:
        return None
    return round(sum(numbers) / len(numbers), 2)


def _month_key(value: datetime | None) -> str | None:
    if not value:
        return None
    return value.strftime("%Y-%m")


def _month_label(month_key: str, include_year: bool) -> str:
    date_value = datetime.strptime(month_key, "%Y-%m")
    return date_value.strftime("%b %Y" if include_year else "%b")


def _day_key(value: datetime | None) -> str | None:
    if not value:
        return None
    return value.strftime("%Y-%m-%d")


def _day_label(day_key: str) -> str:
    date_value = datetime.strptime(day_key, "%Y-%m-%d")
    return date_value.strftime("%d")


def _rating_label(value: object) -> str | None:
    if value is None or value == "":
        return None
    numeric = _safe_number(value)
    if numeric is not None:
        rating = int(round(float(numeric)))
        return {1: "A", 2: "B", 3: "C", 4: "D", 5: "E"}.get(rating, str(value))
    text = str(value).strip()
    return text or None


def _most_common_or_latest(values: list[object]) -> str | None:
    labels = [_rating_label(value) for value in values]
    labels = [label for label in labels if label]
    if not labels:
        return None
    counts = Counter(labels)
    return max(enumerate(labels), key=lambda item: (counts[item[1]], item[0]))[1]


def _health_status(score: float | None) -> str:
    if score is None:
        return "Unavailable"
    if score >= 90:
        return "🟢 Excellent"
    if score >= 75:
        return "🟢 Good"
    if score >= 60:
        return "🟡 Fair"
    if score >= 40:
        return "🟠 Needs Improvement"
    return "🔴 Poor"


def _security_status(score: float | None) -> str:
    if score is None:
        return "Unavailable"
    if score >= 95:
        return "🟢 Excellent"
    if score >= 80:
        return "🟢 Good"
    if score >= 60:
        return "🟡 Moderate Risk"
    if score >= 40:
        return "🟠 High Risk"
    return "🔴 Critical Risk"


def _security_status_label(score: float | None) -> str:
    if score is None:
        return "Unavailable"
    if score >= 95:
        return "Excellent"
    if score >= 80:
        return "Good"
    if score >= 60:
        return "Moderate Risk"
    if score >= 40:
        return "High Risk"
    return "Critical Risk"


def _security_risk_level_from_score(score: float | int | None) -> str:
    numeric = _safe_number(score)
    if numeric is None:
        return "Unavailable"
    if numeric >= 90:
        return "Low"
    if numeric >= 70:
        return "Medium"
    if numeric >= 50:
        return "High"
    return "Critical"


def _security_breakdown_for_run(db: Session, run_id: int, security_score: object | None) -> dict:
    findings = db.query(SecurityFinding).filter(SecurityFinding.analysis_run_id == run_id).all()
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for finding in findings:
        severity = str(finding.severity or "").upper()
        if severity in {"CRITICAL", "BLOCKER"}:
            counts["critical"] += 1
        elif severity in {"HIGH", "MAJOR"}:
            counts["high"] += 1
        elif severity == "MEDIUM":
            counts["medium"] += 1
        else:
            counts["low"] += 1

    rounded_score = _round_metric(security_score)
    return {
        "score": rounded_score,
        "status": _security_status_label(float(rounded_score) if rounded_score is not None else None),
        "risk_level": _security_risk_level_from_score(rounded_score),
        "findings_count": len(findings),
        "breakdown": counts,
    }


def _numeric_measure_map(measures: object) -> dict:
    if not isinstance(measures, dict):
        return {}
    return {key: _safe_number(value) for key, value in measures.items()}


def _count_issues_by_type(issues) -> dict[str, int]:
    counts = {"BUG": 0, "CODE_SMELL": 0}
    for issue in issues or []:
        issue_type = str(getattr(issue, "type", "") or "").upper()
        if issue_type in counts:
            counts[issue_type] += 1
    return counts


def _skill_score_fields(
    score_row: SkillScore | None,
    sonar_health_score: object | None = None,
    security_score: object | None = None,
) -> dict:
    return build_skill_score_fields(
        score_row,
        sonar_health_score=sonar_health_score,
        security_score=security_score,
    )


safe_number = _safe_number
avg_present = _avg_present
rating_label = _rating_label


def _round_metric(value: object) -> float | int | None:
    numeric = _safe_number(value)
    if numeric is None:
        return None
    return round(float(numeric), 2)


def _sonar_summary_for_dashboard(
    run: AnalysisRun,
    summary: SonarAnalysisSummary | None,
) -> dict:
    if summary:
        measures = _numeric_measure_map(summary.measures)
        coverage_value = measures.get("coverage")
        return {
            "sonar_health_score": _round_metric(summary.sonar_health_score),
            "sonar_state": "ready" if summary.sonar_health_score is not None else "sonar_unavailable",
            "quality_gate": summary.quality_gate,
            "bugs": _safe_number(measures.get("bugs")),
            "code_smells": _safe_number(measures.get("code_smells")),
            "coverage": _safe_number(coverage_value),
            "duplication_percentage": _safe_number(measures.get("duplicated_lines_density")),
            "cognitive_complexity": _safe_number(measures.get("cognitive_complexity")),
            "reliability_rating": _rating_label(measures.get("reliability_rating")),
            "maintainability_rating": _rating_label(measures.get("sqale_rating")),
            "technical_debt_minutes": _safe_number(measures.get("sqale_index")),
            "lines_of_code": _safe_number(measures.get("ncloc")),
        }

    sonar_payload = get_sonar_payload(run)
    measures = get_sonar_measure_map(sonar_payload)
    coverage_meta = get_coverage_metadata(sonar_payload)
    sonar_health_score = compute_sonar_health_score(sonar_payload)
    return {
        "sonar_health_score": _round_metric(sonar_health_score),
        "sonar_state": "ready" if sonar_health_score is not None else "sonar_unavailable",
        "quality_gate": get_sonar_quality_gate_status(sonar_payload),
        "bugs": _safe_number(measures.get("bugs")) if sonar_payload else None,
        "code_smells": _safe_number(measures.get("code_smells")) if sonar_payload else None,
        "coverage": _safe_number(measures.get("coverage")) if sonar_payload and coverage_meta.get("available") else None,
        "duplication_percentage": _safe_number(measures.get("duplicated_lines_density")) if sonar_payload else None,
        "cognitive_complexity": _safe_number(measures.get("cognitive_complexity")) if sonar_payload else None,
        "reliability_rating": _rating_label(measures.get("reliability_rating")) if sonar_payload else None,
        "maintainability_rating": _rating_label(measures.get("sqale_rating")) if sonar_payload else None,
        "technical_debt_minutes": _safe_number(measures.get("sqale_index")) if sonar_payload else None,
        "lines_of_code": _safe_number(measures.get("ncloc")) if sonar_payload else None,
    }


def build_candidate_dashboard_row(
    run: AnalysisRun,
    repo: Repository,
    score: SkillScore,
    candidate: RecruiterCandidate,
    sonar_summary: SonarAnalysisSummary | None = None,
    task: RecruiterTask | None = None,
    repo_count: int = 1,
    contribution_count: int = 1,
) -> dict:
    sonar = _sonar_summary_for_dashboard(run, sonar_summary)
    security_score = _round_metric(getattr(score, "security_awareness_score", None))
    skill_fields = _skill_score_fields(
        score,
        sonar_health_score=sonar["sonar_health_score"],
        security_score=security_score,
    )
    return {
        "candidate_name": candidate.candidate_name,
        "github_login": candidate.github_login or "",
        "github_avatar_url": candidate.github_avatar_url,
        "repo_name": repo.name or repo.full_name or "",
        "repo_url": repo.url,
        "task_id": candidate.task_id,
        "task_title": task.title if task else None,
        "skill_score": _round_metric(skill_fields.get("skill_score")),
        "skill_score_level": skill_fields.get("skill_score_level") or "Unavailable",
        "sonar_health_score": sonar["sonar_health_score"],
        "sonar_state": sonar["sonar_state"],
        "security": security_score,
        "quality_gate": sonar["quality_gate"],
        "bugs": sonar["bugs"],
        "code_smells": sonar["code_smells"],
        "coverage": sonar["coverage"],
        "duplication_percentage": sonar["duplication_percentage"],
        "cognitive_complexity": sonar["cognitive_complexity"],
        "reliability_rating": sonar["reliability_rating"],
        "maintainability_rating": sonar["maintainability_rating"],
        "technical_debt_minutes": sonar["technical_debt_minutes"],
        "lines_of_code": sonar["lines_of_code"],
        "repo_count": int(repo_count or 1),
        "contribution_count": int(contribution_count or 0),
        "run_id": run.id,
        "analysis_status": run.status,
        "completed_at": run.completed_at,
    }


def _candidate_identity(row: dict) -> str:
    return str(row.get("github_login") or row.get("candidate_name") or row.get("run_id") or "").strip().lower()


def _rating_rank(label: object) -> int | None:
    text = _rating_label(label)
    if not text:
        return None
    return {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5}.get(str(text).upper())


def _risk_from_score(score: object, medium: float, high: float, critical: float) -> str:
    numeric = _safe_number(score)
    if numeric is None:
        return "medium"
    value = float(numeric)
    if value < critical:
        return "critical"
    if value < high:
        return "high"
    if value < medium:
        return "medium"
    return "low"


def _code_quality_risk(row: dict) -> str:
    bugs = _safe_number(row.get("bugs")) or 0
    smells = _safe_number(row.get("code_smells")) or 0
    score = _safe_number(row.get("skill_score")) or 0
    if bugs > 10 or smells > 100 or score < 50:
        return "critical"
    if bugs > 5 or smells > 50 or score < 60:
        return "high"
    if bugs > 2 or smells > 20 or score < 75:
        return "medium"
    return "low"


def _security_risk(row: dict) -> str:
    return _risk_from_score(row.get("security"), medium=85, high=70, critical=50)


def _maintainability_risk(row: dict) -> str:
    rating = _rating_rank(row.get("maintainability_rating"))
    debt = _safe_number(row.get("technical_debt_minutes")) or 0
    duplication = _safe_number(row.get("duplication_percentage")) or 0
    if rating and rating >= 5 or debt > 240 or duplication > 15:
        return "critical"
    if rating and rating >= 4 or debt > 60 or duplication > 10:
        return "high"
    if rating and rating >= 3 or debt > 30 or duplication > 5:
        return "medium"
    return "low"


def _testing_risk(row: dict) -> str:
    return _risk_from_score(row.get("coverage"), medium=80, high=60, critical=40)


def _reliability_risk(row: dict) -> str:
    rating = _rating_rank(row.get("reliability_rating"))
    bugs = _safe_number(row.get("bugs")) or 0
    if rating and rating >= 5 or bugs > 10:
        return "critical"
    if rating and rating >= 4 or bugs > 5:
        return "high"
    if rating and rating >= 3 or bugs > 2:
        return "medium"
    return "low"


def build_risk_heatmap(rows: list[dict]) -> list[dict]:
    return [
        {
            "candidate_name": row["candidate_name"],
            "code_quality": _code_quality_risk(row),
            "security": _security_risk(row),
            "maintainability": _maintainability_risk(row),
            "testing": _testing_risk(row),
            "reliability": _reliability_risk(row),
        }
        for row in rows
    ]


def build_task_distribution(rows: list[dict]) -> dict:
    distribution = {"excellent": 0, "good": 0, "fair": 0, "poor": 0}
    for row in rows:
        score = _safe_number(row.get("skill_score"))
        if score is None or score < 60:
            distribution["poor"] += 1
        elif score < 70:
            distribution["fair"] += 1
        elif score < 90:
            distribution["good"] += 1
        else:
            distribution["excellent"] += 1
    return distribution


def _overview(rows: list[dict], current_user: User) -> dict:
    gates = [str(row.get("quality_gate") or "").upper() for row in rows if row.get("quality_gate")]
    pass_count = len([gate for gate in gates if gate in {"PASS", "OK", "PASSED"}])
    threshold = _safe_number(getattr(current_user, "high_priority_threshold", None))
    threshold = float(threshold) if threshold is not None else 75.0
    return {
        "total_candidates": len(rows),
        "average_skill_score": _avg_present([row.get("skill_score") for row in rows]),
        "average_sonar_health": _avg_present([row.get("sonar_health_score") for row in rows]),
        "average_security_score": _avg_present([row.get("security") for row in rows]),
        "passed_quality_gate_percentage": round((pass_count / len(gates)) * 100, 2) if gates else 0,
        "high_priority_candidates": len([
            row for row in rows
            if (_safe_number(row.get("skill_score")) is not None and float(_safe_number(row.get("skill_score"))) >= threshold)
        ]),
    }


def _summary_candidate_from_row(row: dict, cached: dict | None = None) -> dict:
    insight = (cached or {}).get("insight") if isinstance(cached, dict) else None
    generated_at = (cached or {}).get("generated_at") if isinstance(cached, dict) else None
    model_source = (cached or {}).get("model_source") if isinstance(cached, dict) else None
    if not isinstance(insight, dict):
        insight = {
            "summary": f"{row['candidate_name']} demonstrates task performance based on the available analysis metrics.",
            "strengths": ["Completed repository analysis"],
            "areas_to_improve": ["Monitor technical debt"],
            "recommendation": "interview" if (_safe_number(row.get("skill_score")) or 0) >= 75 else "review_required",
            "recommendation_reason": "Deterministic summary based on available dashboard metrics.",
            "risk_level": max(
                [_code_quality_risk(row), _security_risk(row), _maintainability_risk(row), _testing_risk(row), _reliability_risk(row)],
                key={"low": 0, "medium": 1, "high": 2, "critical": 3}.get,
            ),
        }
        generated_by = "summary"
    else:
        generated_by = "fallback" if model_source == "fallback" else "llm"

    return {
        "candidate_name": row["candidate_name"],
        "github_login": row.get("github_login") or "",
        "github_avatar_url": row.get("github_avatar_url"),
        "run_id": row["run_id"],
        "repo_name": row["repo_name"],
        "task_title": row.get("task_title"),
        "skill_score": row.get("skill_score"),
        "sonar_health_score": row.get("sonar_health_score"),
        "security": row.get("security"),
        "coverage": row.get("coverage"),
        "bugs": row.get("bugs"),
        "summary": insight.get("summary") or "",
        "strengths": insight.get("strengths") or [],
        "areas_to_improve": insight.get("areas_to_improve") or [],
        "recommendation": insight.get("recommendation") or "review_required",
        "recommendation_reason": insight.get("recommendation_reason"),
        "risk_level": insight.get("risk_level") or "medium",
        "generated_by": generated_by,
        "generated_at": generated_at,
    }


def build_dashboard_summary(rows: list[dict], current_user: User, runs_by_id: dict[int, AnalysisRun] | None = None) -> dict:
    top_row = None
    scored_rows = [row for row in rows if _safe_number(row.get("skill_score")) is not None]
    if scored_rows:
        top_row = max(scored_rows, key=lambda row: float(_safe_number(row.get("skill_score")) or 0))

    cached = None
    if top_row and runs_by_id:
        cached = get_cached_recruiter_candidate_insight(runs_by_id.get(top_row["run_id"]))

    return {
        "overview": _overview(rows, current_user),
        "task_distribution": build_task_distribution(rows),
        "risk_heatmap": build_risk_heatmap(rows),
        "top_candidate": _summary_candidate_from_row(top_row, cached) if top_row else None,
    }


def _compact_sonar_issue(row: SonarIssue) -> dict:
    return {
        "type": row.type,
        "severity": row.severity,
        "file_path": row.file_path,
        "line": row.line,
        "rule": row.rule,
        "message": row.message,
    }


def _compact_security_finding(row: SecurityFinding) -> dict:
    return {
        "tool": row.tool,
        "rule": row.rule,
        "cwe": row.cwe,
        "file_path": row.file_path,
        "severity": row.severity,
        "description": row.description,
        "line_number": row.line_number,
        "owasp_category": row.owasp_category,
    }


def _compact_risky_file(row: SonarFileMeasure) -> dict:
    return {
        "file_path": row.file_path,
        "coverage": _safe_number(row.coverage),
        "duplicated_lines_density": _safe_number(row.duplicated_lines_density),
        "ncloc": _safe_number(row.ncloc),
        "complexity": _safe_number(row.complexity),
        "cognitive_complexity": _safe_number(row.cognitive_complexity),
    }


def build_recruiter_candidate_llm_payload(
    row: dict,
    run: AnalysisRun,
    repo: Repository,
    candidate: RecruiterCandidate,
    task: RecruiterTask | None,
    sonar_issues: list[SonarIssue],
    security_findings: list[SecurityFinding],
    risky_files: list[SonarFileMeasure],
) -> dict:
    return {
        "candidate": {
            "name": candidate.candidate_name,
            "github_login": candidate.github_login,
            "task_title": task.title if task else None,
        },
        "repository": {
            "name": repo.name,
            "full_name": repo.full_name,
            "url": repo.url,
            "branch": run.branch,
        },
        "scores": {
            "skill_score": row.get("skill_score"),
            "skill_score_level": row.get("skill_score_level"),
            "sonar_health_score": row.get("sonar_health_score"),
            "security_score": row.get("security"),
            "quality_gate": row.get("quality_gate"),
        },
        "sonar_metrics": {
            "bugs": row.get("bugs"),
            "code_smells": row.get("code_smells"),
            "coverage": row.get("coverage"),
            "duplication_percentage": row.get("duplication_percentage"),
            "cognitive_complexity": row.get("cognitive_complexity"),
            "technical_debt_minutes": row.get("technical_debt_minutes"),
            "lines_of_code": row.get("lines_of_code"),
            "reliability_rating": row.get("reliability_rating"),
            "maintainability_rating": row.get("maintainability_rating"),
        },
        "top_sonar_issues": [_compact_sonar_issue(item) for item in sonar_issues[:10]],
        "top_security_findings": [_compact_security_finding(item) for item in security_findings[:10]],
        "risky_files": [_compact_risky_file(item) for item in risky_files[:10]],
    }


def get_cached_recruiter_candidate_insight(run: AnalysisRun | None) -> dict | None:
    ai_insights = getattr(run, "ai_insights", None)
    if not isinstance(ai_insights, dict):
        return None
    cached = ai_insights.get("recruiter_candidate_insight")
    if not isinstance(cached, dict):
        return None
    insight = cached.get("insight")
    if not isinstance(insight, dict):
        return None
    return cached


def set_cached_recruiter_candidate_insight(
    run: AnalysisRun,
    insight: dict,
    model_source: str,
) -> dict:
    generated_at = datetime.now(timezone.utc).isoformat()
    cache_payload = {
        "generated_at": generated_at,
        "model_source": model_source,
        "payload_version": 1,
        "insight": insight,
    }
    ai_insights = run.ai_insights if isinstance(run.ai_insights, dict) else {}
    ai_insights = dict(ai_insights)
    ai_insights["recruiter_candidate_insight"] = cache_payload
    run.ai_insights = ai_insights
    flag_modified(run, "ai_insights")
    return cache_payload


def _without_removed_skill_score_outputs(ai_insights: object) -> object:
    if not isinstance(ai_insights, dict):
        return ai_insights
    sanitized = dict(ai_insights)
    for key in (
        "llm_problem_solving",
        "llm_skill_scores",
        "llm_adjustment_guidance",
        "architecture_metrics",
        "skills_insights",
    ):
        sanitized.pop(key, None)
    return sanitized


def _normalise_identity(value: object) -> str | None:
    if value is None:
        return None
    normalised = str(value).strip().lower()
    return normalised or None


def _commit_matches_developer(commit_record: dict, developer: User) -> bool:
    login = _normalise_identity(commit_record.get("login"))
    github_id = _normalise_identity(commit_record.get("github_id"))
    emails = {
        _normalise_identity(email)
        for email in (commit_record.get("emails") or [])
    }
    emails.discard(None)

    developer_github_id = _normalise_identity(developer.github_id)
    developer_username = _normalise_identity(developer.username)
    developer_email = _normalise_identity(developer.work_email)

    return (
        bool(developer_github_id and github_id == developer_github_id)
        or bool(developer_username and login == developer_username)
        or bool(developer_email and developer_email in emails)
    )


def _build_manager_contributor_scopes(
    developers: list[User],
    commit_records: list[dict],
) -> list[dict]:
    contributor_scopes: list[dict] = []

    for developer in developers:
        touched_files: set[str] = set()
        matched_login: str | None = None
        matched_email: str | None = None

        for record in commit_records:
            if not _commit_matches_developer(record, developer):
                continue

            if not matched_login and record.get("login"):
                matched_login = str(record["login"])
            if not matched_email and record.get("emails"):
                matched_email = str(record["emails"][0])

            for file_path in record.get("touched_files") or []:
                if file_path:
                    touched_files.add(str(file_path).replace("\\", "/"))

        python_touched_files = sorted(path for path in touched_files if path.endswith(".py"))
        if not python_touched_files:
            continue

        contributor_scopes.append({
            "user_id": developer.id,
            "contributor_login": matched_login or developer.username or matched_email,
            "touched_files": sorted(touched_files),
            "python_touched_files": python_touched_files,
        })

    return contributor_scopes


def _link_repository_contributors(
    db: Session,
    repo_id: int,
    contributor_scopes: list[dict],
) -> None:
    for contributor in contributor_scopes:
        user_id = contributor.get("user_id")
        if not user_id:
            continue
        link_exists = (
            db.query(RepositoryContributor)
            .filter(
                RepositoryContributor.repository_id == repo_id,
                RepositoryContributor.user_id == user_id,
            )
            .first()
        )
        if not link_exists:
            db.add(RepositoryContributor(
                repository_id=repo_id,
                user_id=user_id,
            ))
    db.commit()


@router.post("/run")
@limiter.limit("2/minute")
async def run_analysis(
    request: Request,
    data: RepoRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _run_analysis_impl(
        request=request,
        data=data,
        background_tasks=background_tasks,
        db=db,
        current_user=current_user,
    )


def _safe_uploaded_coverage_filename(filename: str | None) -> str:
    original = os.path.basename(filename or "coverage.xml")
    if not original.lower().endswith(".xml"):
        raise HTTPException(status_code=400, detail="Coverage report must be an XML file.")
    return f"coverage_{uuid.uuid4().hex}.xml"


async def _save_uploaded_coverage_report(coverage_file: UploadFile | None) -> str | None:
    if coverage_file is None or not coverage_file.filename:
        return None

    safe_name = _safe_uploaded_coverage_filename(coverage_file.filename)
    upload_dir = os.path.join(tempfile.gettempdir(), "skillpulse_coverage_uploads")
    os.makedirs(upload_dir, exist_ok=True)
    target_path = os.path.join(upload_dir, safe_name)

    max_bytes = 10 * 1024 * 1024
    total = 0
    with open(target_path, "wb") as output:
        while True:
            chunk = await coverage_file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                output.close()
                try:
                    os.remove(target_path)
                except OSError:
                    pass
                raise HTTPException(status_code=400, detail="Coverage report is too large. Maximum size is 10MB.")
            output.write(chunk)

    with open(target_path, "rb") as check_file:
        head = check_file.read(500).lstrip()
    if not (head.startswith(b"<?xml") or b"<coverage" in head or b"<report" in head):
        try:
            os.remove(target_path)
        except OSError:
            pass
        raise HTTPException(status_code=400, detail="Uploaded file does not look like a coverage XML report.")

    return target_path


@router.post("/run/with-coverage")
@limiter.limit("2/minute")
async def run_analysis_with_optional_coverage(
    request: Request,
    background_tasks: BackgroundTasks,
    repo_url: str = Form(...),
    branch: str = Form("main"),
    programming_language: str = Form("python"),
    coverage_file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    print("repo_url:", repo_url)
    print("branch:", branch)
    print("programming_language:", programming_language)
    print("coverage_file:", coverage_file.filename if coverage_file else None)
    coverage_report_path = await _save_uploaded_coverage_report(coverage_file)
    return await _run_analysis_impl(
        request=request,
        data=RepoRequest(
            repo_url=repo_url,
            branch=branch,
            programming_language=programming_language,
        ),
        background_tasks=background_tasks,
        db=db,
        current_user=current_user,
        coverage_report_path=coverage_report_path,
    )


async def _run_analysis_impl(
    request: Request,
    data: RepoRequest,
    background_tasks: BackgroundTasks,
    db: Session,
    current_user: User,
    coverage_report_path: str | None = None,
):
    if not re.match(r"^https://github\.com/[^/]+/[^/]+", data.repo_url):
        raise HTTPException(status_code=400, detail="Invalid GitHub repository URL")
    
    full_name = data.repo_url.replace("https://github.com/", "").replace(".git", "")
    repo_name = full_name.split("/")[-1]
    
    token = decrypt_github_token(current_user.github_access_token) if current_user.github_access_token else None
    user_role = current_user.role.value if current_user.role else None
    is_developer = user_role == "developer"
    is_manager = user_role == "manager"

    if is_developer and not token:
        raise HTTPException(
            status_code=403,
                detail=build_github_connect_payload(request, current_user)
        )

    if (
        token
        and current_user.github_token_expires_at
        and current_user.github_token_expires_at <= datetime.now(timezone.utc)
    ):
        refreshed_token = await refresh_github_access_token_for_user(db, current_user)
        if refreshed_token:
            token = refreshed_token
    
    repo_data = None
    
    if token:
        try:
            repo_data = await verify_repo_access(token, full_name)
        except HTTPException as e:
            if e.status_code == 401:
                refreshed_token = await refresh_github_access_token_for_user(db, current_user)
                if refreshed_token:
                    token = refreshed_token
                    repo_data = await verify_repo_access(token, full_name)
                else:
                    payload = build_github_connect_payload(request, current_user)
                    payload["reason"] = "github_token_expired"
                    raise HTTPException(status_code=403, detail=payload)
            else:
                raise
    else:
        try:
            repo_data = await verify_repo_access(None, full_name)
        except HTTPException as e:
            if e.status_code == 404:
                if user_role == "recruiter":
                    raise HTTPException(
                        status_code=403,
                        detail={"recruiter_private_repo": True}
                    )

                raise HTTPException(
                    status_code=403,
                    detail=build_github_connect_payload(request, current_user)
                )
            raise
    # try:
    #     repo_data = await verify_repo_access(token, full_name)
    # except HTTPException as e:
    #     if e.status_code == 404 and not token:
    #         # Recruiters can't access private repos — show specific message
    #         if current_user.role.value == "recruiter":
    #             raise HTTPException(
    #                 status_code=403,
    #                 detail={"recruiter_private_repo": True}
    #             )
    #         # Other users without token — prompt GitHub connect
    #         auth_header = request.headers.get("authorization")
    #         if not auth_header:
    #             raise HTTPException(status_code=401, detail="Missing Authorization header")
    #         jwt_token = auth_header.split(" ")[1]
    #         raise HTTPException(
    #             status_code=403,
    #             detail={
    #                 "requires_github_auth": True,
    #                 "auth_url": f"http://127.0.0.1:8000/auth/github?action=connect&token={jwt_token}"
    #             }
    #         )
    #     if e.status_code == 403:
    #         raise HTTPException(
    #             status_code=503,
    #             detail="GitHub API rate limit reached. Connect your GitHub account or wait a moment and try again."
    #         )
    #     if e.status_code == 404:
    #         raise HTTPException(status_code=404, detail="Repository not found or inaccessible")
    #     raise

    is_private = repo_data.get("private", False)

    if is_private and user_role == "recruiter":
        raise HTTPException(
            status_code=403,
            detail={"recruiter_private_repo": True}
        )

    head_sha = await get_branch_head_sha(token, full_name, data.branch)
    if not head_sha:
        raise HTTPException(
            status_code=404,
            detail={
                "branch_not_found": True,
                "message": "Repository found, but this branch does not exist or is not accessible.",
            },
        )

    contributor_login = None
    contribution_context = None
    analysis_scope = "repository"
    touched_files: list[str] = []
    cache_sha = head_sha

    if is_developer:
        _, contributor_login = await resolve_github_identity(db, current_user)
        try:
            contribution_context = await fetch_user_repo_contribution_summary(
                token,
                full_name,
                contributor_login,
                data.branch,
            )
        except HTTPException as e:
            if e.status_code in {404, 422, 502}:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "branch_not_found": True,
                        "message": "Repository found, but this branch does not exist or is not accessible.",
                    },
                )
            raise
        touched_files = contribution_context.get("touched_files", [])
        python_touched_files = [p for p in touched_files if p.endswith(".py")]

        if not contribution_context.get("user_contributed"):
            raise HTTPException(
                status_code=403,
                detail={
                    "no_developer_contributions": True,
                    "message": "SkillPulse analyzes your own GitHub contributions. We could not find commits from your GitHub account in this repository.",
                },
            )

        if not python_touched_files:
            raise HTTPException(
                status_code=400,
                detail={
                    "no_python_contributions": True,
                    "message": "We found your commits, but none of the touched files are Python files that SkillPulse can analyze yet.",
                },
            )

        analysis_scope = "contribution"
        python_contribution_fingerprint = await get_files_fingerprint(
            token,
            full_name,
            data.branch,
            python_touched_files,
        )
        if not python_contribution_fingerprint:
            raise HTTPException(
                status_code=400,
                detail={
                    "no_python_contributions": True,
                    "message": "We found your commits, but none of the touched Python files are present on this branch anymore.",
                },
            )
        contribution_fingerprint = await get_files_fingerprint(
            token,
            full_name,
            data.branch,
            touched_files,
        ) or python_contribution_fingerprint
        cache_sha = contribution_fingerprint

    # Get or Create Repo
    repo = db.query(Repository).filter(Repository.github_repo_id == str(repo_data["id"])).first()
    if not repo:
        repo = Repository(
            name=repo_name,
            full_name=full_name,
            url=data.repo_url,
            github_repo_id=str(repo_data["id"]) if repo_data else None,
            is_private=is_private,
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)

    # ── Incremental analysis: skip re-analysis if the relevant snapshot has not changed ──
    if cache_sha and not coverage_report_path:
        existing_run_query = (
            db.query(AnalysisRun)
            .filter(
                AnalysisRun.repository_id == repo.id,
                AnalysisRun.branch == data.branch,
                AnalysisRun.commit_sha == cache_sha,
                AnalysisRun.status == "completed",
                AnalysisRun.analysis_scope == analysis_scope,
            )
        )
        if is_manager:
            existing_run_query = existing_run_query.filter(AnalysisRun.user_id == current_user.id)

        existing_run = existing_run_query.order_by(AnalysisRun.triggered_at.desc()).first()
        if existing_run and not _analysis_has_sonar_dashboard(existing_run):
            existing_run = None

        if existing_run:
            if is_manager:
                background_tasks.add_task(
                    background_manager_contributor_analysis_task,
                    repository_run_id=existing_run.id,
                    repo_id=repo.id,
                    repo_url=data.repo_url,
                    repo_name=repo_name,
                    branch=data.branch,
                    full_name=full_name,
                    token=token,
                    is_private=is_private,
                    manager_user_id=current_user.id,
                )
                score_row = (
                    db.query(SkillScore)
                    .filter(
                        SkillScore.analysis_run_id == existing_run.id,
                        SkillScore.user_id == current_user.id,
                    )
                    .first()
                )
                sonar_summary = build_sonar_repo_summary(existing_run)
                skill_fields = _skill_score_fields(
                    score_row,
                    sonar_health_score=sonar_summary["sonar_health_score"],
                    security_score=getattr(score_row, "security_awareness_score", None),
                )
                return {
                    "message": "Repository is up to date. Returning cached repository results.",
                    "run_id": existing_run.id,
                    "analysis_run_id": existing_run.id,
                    "repo_id": repo.id,
                    "repo_name": repo.name,
                    "branch": existing_run.branch,
                    "status": "completed",
                    "cached": True,
                    "cached_scope": analysis_scope,
                    "cached_for_current_user": True,
                    **skill_fields,
                    "sonar_health_score": sonar_summary["sonar_health_score"],
                    "sonar_state": sonar_summary["sonar_state"],
                    "quality_gate": sonar_summary["quality_gate"],
                }

        if existing_run and not is_manager:
            cached_for_current_user = score_belongs_to_user(db, existing_run.id, current_user.id)
            if link_existing_run_to_user(db, existing_run, current_user.id):
                return {
                    "message": (
                        "Your contribution scope is up to date. Returning cached results."
                        if cached_for_current_user
                        else "Existing analysis results are ready for this contribution scope."
                    ),
                    "run_id": existing_run.id,
                    "analysis_run_id": existing_run.id,
                    "repo_id": repo.id,
                    "repo_name": repo.name,
                    "branch": existing_run.branch,
                    "status": "completed",
                    "cached": True,
                    "cached_scope": analysis_scope,
                    "cached_for_current_user": cached_for_current_user,
                }

    # Create Analysis Run (Pending/Running)
    run = AnalysisRun(
        repository_id=repo.id,
        branch=data.branch,
        status="running",
        user_id=current_user.id,
        commit_sha=cache_sha,
        analysis_scope=analysis_scope,
        contributor_login=None if is_manager else contributor_login,
        triggered_at=datetime.now(timezone.utc)
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # Trigger Background Task
    if is_manager:
        background_tasks.add_task(
            background_manager_repository_analysis_task,
            run_id=run.id,
            repo_id=repo.id,
            repo_url=data.repo_url,
            repo_name=repo_name,
            branch=data.branch,
            full_name=full_name,
            token=token,
            is_private=is_private,
            manager_user_id=current_user.id,
            coverage_report_path=coverage_report_path,
        )
    else:
        background_tasks.add_task(
            background_analysis_task,
            run_id=run.id,
            repo_id=repo.id,
            repo_url=data.repo_url,
            repo_name=repo_name,
            branch=data.branch,
            full_name=full_name,
            token=token,
            is_private=is_private,
            current_user_id=current_user.id,
            user_role=user_role,
            analysis_scope=analysis_scope,
            contributor_login=contributor_login,
            touched_files=touched_files,
            coverage_report_path=coverage_report_path,
        )

    # Return Immediately
    return {
        "message": "Analysis started successfully. Running in the background.",
        "run_id": run.id,
        "analysis_run_id": run.id,
        "repo_id": repo.id,
        "repo_name": repo.name,
        "branch": run.branch,
        "status": "running",
        "cached": False,
        "analysis_scope": analysis_scope,
        "contributors_matched": None,
    }
    
@router.get("/history")
async def get_analysis_history(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # linked_completed_runs = (
    #     db.query(AnalysisRun)
    #     .join(SkillScore, SkillScore.analysis_run_id == AnalysisRun.id)
    #     .filter(SkillScore.user_id == current_user.id)
    #     .all()
    # )
    # own_active_runs = (
    #     db.query(AnalysisRun)
    #     .filter(
    #         AnalysisRun.user_id == current_user.id,
    #         AnalysisRun.status != "completed",
    #     )
    #     .all()
    # )

    # unique_runs = {run.id: run for run in linked_completed_runs + own_active_runs}
    linked_runs = (
        db.query(AnalysisRun)
        .join(SkillScore, SkillScore.analysis_run_id == AnalysisRun.id)
        .filter(
            SkillScore.user_id == current_user.id,
            AnalysisRun.user_id == current_user.id,
        )
        .all()
    )
    own_runs_query = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.user_id == current_user.id)
    )
    if current_user.role and current_user.role.value == "manager":
        own_runs_query = own_runs_query.filter(AnalysisRun.analysis_scope == "repository")
    own_runs = own_runs_query.all()

    unique_runs = {run.id: run for run in linked_runs + own_runs}
    past_runs = sorted(
        unique_runs.values(),
        key=lambda run: run.triggered_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )[:limit]

    result = []

    for run in past_runs:
        sonar_summary = build_sonar_repo_summary(run)
        score_row = (
            db.query(SkillScore)
            .filter(
                SkillScore.analysis_run_id == run.id,
                SkillScore.user_id == current_user.id,
            )
            .first()
        )
        skill_fields = _skill_score_fields(
            score_row,
            sonar_health_score=sonar_summary["sonar_health_score"],
            security_score=getattr(score_row, "security_awareness_score", None),
        )

        result.append({
            "analysis_id": run.id,
            "repo_name": run.repository.name,
            "branch": run.branch,
            "status": run.status,
            "triggered_at": run.triggered_at,
            "completed_at": run.completed_at,
            **skill_fields,
            "sonar_health_score": sonar_summary["sonar_health_score"],
            "sonar_state": sonar_summary["sonar_state"],
            "quality_gate": sonar_summary["quality_gate"],
            "bugs": sonar_summary["bugs"],
            "code_smells": sonar_summary["code_smells"],
            "coverage": sonar_summary["coverage"],
            "duplication_percentage": sonar_summary["duplication_percentage"],
            "cognitive_complexity": sonar_summary["cognitive_complexity"],
            "reliability_rating": sonar_summary["reliability_rating"],
            "maintainability_rating": sonar_summary["maintainability_rating"],
            "technical_debt_minutes": sonar_summary["technical_debt_minutes"],
            "lines_of_code": sonar_summary["lines_of_code"],
            "repo_id": run.repository.id,
            "analysis_scope": run.analysis_scope,
        })

    return {"history": result}


def _verify_recruiter_task(
    db: Session,
    current_user: User,
    task_id: int | None,
) -> RecruiterTask | None:
    if task_id is None:
        return None
    task = (
        db.query(RecruiterTask)
        .filter(
            RecruiterTask.id == task_id,
            RecruiterTask.recruiter_id == current_user.id,
        )
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Recruiter task not found")
    return task


def _candidate_query_rows(
    db: Session,
    current_user: User,
    task_id: int | None = None,
) -> list[tuple[AnalysisRun, Repository, SkillScore, RecruiterCandidate, SonarAnalysisSummary | None, RecruiterTask | None]]:
    _verify_recruiter_task(db, current_user, task_id)
    query = (
        db.query(AnalysisRun, Repository, SkillScore, RecruiterCandidate, SonarAnalysisSummary, RecruiterTask)
        .join(Repository, AnalysisRun.repository_id == Repository.id)
        .join(
            SkillScore,
            (SkillScore.analysis_run_id == AnalysisRun.id) & (SkillScore.user_id == current_user.id),
        )
        .join(RecruiterCandidate, RecruiterCandidate.analysis_run_id == AnalysisRun.id)
        .outerjoin(SonarAnalysisSummary, SonarAnalysisSummary.analysis_run_id == AnalysisRun.id)
        .outerjoin(RecruiterTask, RecruiterTask.id == RecruiterCandidate.task_id)
        .filter(
            AnalysisRun.user_id == current_user.id,
            SkillScore.user_id == current_user.id,
            AnalysisRun.status == "completed",
        )
    )
    if task_id is not None:
        query = query.filter(RecruiterCandidate.task_id == task_id)
    return query.all()


def _dashboard_rows_from_query(
    query_rows: list[tuple[AnalysisRun, Repository, SkillScore, RecruiterCandidate, SonarAnalysisSummary | None, RecruiterTask | None]],
    db: Session,
) -> list[dict]:
    run_ids = [run.id for run, *_ in query_rows]
    loc_by_run = {}
    if run_ids:
        loc_by_run = dict(
            db.query(
                CodeMetrics.analysis_run_id,
                func.coalesce(func.sum(CodeMetrics.lines_of_code), 0),
            )
            .filter(CodeMetrics.analysis_run_id.in_(run_ids))
            .group_by(CodeMetrics.analysis_run_id)
            .all()
        )

    repo_counts = Counter(candidate.candidate_name for _, _, _, candidate, _, _ in query_rows)
    rows = [
        build_candidate_dashboard_row(
            run,
            repo,
            score,
            candidate,
            sonar_summary,
            task,
            repo_count=int(repo_counts.get(candidate.candidate_name, 1)),
            contribution_count=int(loc_by_run.get(run.id, 0)),
        )
        for run, repo, score, candidate, sonar_summary, task in query_rows
    ]
    return rows


def _apply_candidate_filters(
    rows: list[dict],
    search: str | None,
    min_skill_score: float | None,
    max_skill_score: float | None,
    min_sonar: float | None,
    max_sonar: float | None,
    min_security: float | None,
    max_security: float | None,
    min_coverage: float | None,
    max_coverage: float | None,
    quality_gate: str | None,
    max_bugs: int | None,
    max_technical_debt_minutes: float | None,
) -> list[dict]:
    def between(value: object, minimum: float | None, maximum: float | None) -> bool:
        numeric = _safe_number(value)
        if numeric is None:
            return minimum is None and maximum is None
        if minimum is not None and float(numeric) < minimum:
            return False
        if maximum is not None and float(numeric) > maximum:
            return False
        return True

    filtered = rows
    if search:
        needle = search.strip().lower()
        filtered = [
            row for row in filtered
            if needle in " ".join([
                str(row.get("candidate_name") or ""),
                str(row.get("github_login") or ""),
                str(row.get("repo_name") or ""),
                str(row.get("repo_url") or ""),
                str(row.get("task_title") or ""),
            ]).lower()
        ]
    if quality_gate:
        gate = quality_gate.strip().upper()
        filtered = [row for row in filtered if str(row.get("quality_gate") or "").upper() == gate]

    return [
        row for row in filtered
        if between(row.get("skill_score"), min_skill_score, max_skill_score)
        and between(row.get("sonar_health_score"), min_sonar, max_sonar)
        and between(row.get("security"), min_security, max_security)
        and between(row.get("coverage"), min_coverage, max_coverage)
        and (max_bugs is None or ((_safe_number(row.get("bugs")) or 0) <= max_bugs))
        and (
            max_technical_debt_minutes is None
            or ((_safe_number(row.get("technical_debt_minutes")) or 0) <= max_technical_debt_minutes)
        )
    ]


def _sort_candidate_rows(rows: list[dict], sort_by: str, sort_dir: str) -> list[dict]:
    sort_map = {
        "skill_score": "skill_score",
        "sonar_health_score": "sonar_health_score",
        "security": "security",
        "coverage": "coverage",
        "bugs": "bugs",
        "code_smells": "code_smells",
        "technical_debt_minutes": "technical_debt_minutes",
        "completed_at": "completed_at",
    }
    if sort_by not in sort_map:
        raise HTTPException(status_code=400, detail="Invalid sort_by")
    if sort_dir not in {"asc", "desc"}:
        raise HTTPException(status_code=400, detail="Invalid sort_dir")

    key_name = sort_map[sort_by]

    def sort_key(row: dict):
        value = row.get(key_name)
        if key_name == "completed_at":
            return value or MIN_AWARE_DATETIME
        numeric = _safe_number(value)
        return float(numeric) if numeric is not None else -1.0

    return sorted(rows, key=sort_key, reverse=(sort_dir == "desc"))


@router.get("/recruiter/tasks", response_model=list[RecruiterTaskResponse])
async def get_recruiter_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["recruiter"])),
):
    tasks = (
        db.query(RecruiterTask)
        .filter(RecruiterTask.recruiter_id == current_user.id)
        .order_by(RecruiterTask.created_at.desc(), RecruiterTask.id.desc())
        .all()
    )
    if not tasks:
        return []

    task_ids = [task.id for task in tasks]
    analyzed_counts = dict(
        db.query(RecruiterCandidate.task_id, func.count(AnalysisRun.id))
        .join(AnalysisRun, RecruiterCandidate.analysis_run_id == AnalysisRun.id)
        .filter(
            RecruiterCandidate.task_id.in_(task_ids),
            AnalysisRun.user_id == current_user.id,
            AnalysisRun.status == "completed",
        )
        .group_by(RecruiterCandidate.task_id)
        .all()
    )
    average_scores = dict(
        db.query(RecruiterCandidate.task_id, func.avg(SkillScore.overall_score))
        .join(AnalysisRun, RecruiterCandidate.analysis_run_id == AnalysisRun.id)
        .join(SkillScore, SkillScore.analysis_run_id == AnalysisRun.id)
        .filter(
            RecruiterCandidate.task_id.in_(task_ids),
            AnalysisRun.user_id == current_user.id,
            AnalysisRun.status == "completed",
            SkillScore.user_id == current_user.id,
        )
        .group_by(RecruiterCandidate.task_id)
        .all()
    )

    response = []
    for task in tasks:
        analyzed_count = int(analyzed_counts.get(task.id, 0))
        status = task.status
        if status == "analyzing" and task.valid_count and analyzed_count >= task.valid_count:
            status = "completed"
        avg_score = average_scores.get(task.id)
        response.append(RecruiterTaskResponse(
            id=task.id,
            title=task.title,
            csv_filename=task.csv_filename,
            total_candidates=task.total_candidates or 0,
            valid_count=task.valid_count or 0,
            skipped_count=task.skipped_count or 0,
            status=status,
            created_at=task.created_at,
            updated_at=task.updated_at,
            analyzed_count=analyzed_count,
            average_skill_score=round(float(avg_score), 2) if avg_score is not None else None,
        ))
    return response


@router.get("/recruiter/candidates", response_model=list[RecruiterCandidateDashboardRow])
async def get_recruiter_candidates(
    task_id: int | None = Query(None),
    search: str | None = Query(None),
    min_skill_score: float | None = Query(None),
    max_skill_score: float | None = Query(None),
    min_sonar: float | None = Query(None),
    max_sonar: float | None = Query(None),
    min_security: float | None = Query(None),
    max_security: float | None = Query(None),
    min_coverage: float | None = Query(None),
    max_coverage: float | None = Query(None),
    quality_gate: str | None = Query(None),
    max_bugs: int | None = Query(None),
    max_technical_debt_minutes: float | None = Query(None),
    sort_by: str = Query("skill_score"),
    sort_dir: str = Query("desc"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["recruiter"])),
):
    query_rows = _candidate_query_rows(db, current_user, task_id)
    rows = _dashboard_rows_from_query(query_rows, db)
    rows = _apply_candidate_filters(
        rows,
        search,
        min_skill_score,
        max_skill_score,
        min_sonar,
        max_sonar,
        min_security,
        max_security,
        min_coverage,
        max_coverage,
        quality_gate,
        max_bugs,
        max_technical_debt_minutes,
    )
    return [RecruiterCandidateDashboardRow(**row) for row in _sort_candidate_rows(rows, sort_by, sort_dir)]


@router.get("/recruiter/dashboard-summary", response_model=RecruiterDashboardSummaryResponse)
async def get_recruiter_dashboard_summary(
    task_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["recruiter"])),
):
    query_rows = _candidate_query_rows(db, current_user, task_id)
    rows = _dashboard_rows_from_query(query_rows, db)
    runs_by_id = {run.id: run for run, *_ in query_rows}
    return RecruiterDashboardSummaryResponse(**build_dashboard_summary(rows, current_user, runs_by_id))


def _severity_rank(value: object) -> int:
    text = str(value or "").upper()
    return {
        "BLOCKER": 0,
        "CRITICAL": 1,
        "HIGH": 2,
        "MAJOR": 2,
        "MEDIUM": 3,
        "MINOR": 4,
        "LOW": 5,
        "INFO": 6,
    }.get(text, 9)


def _risky_file_rank(row: SonarFileMeasure) -> float:
    return float(_safe_number(row.cognitive_complexity) or 0) + float(_safe_number(row.duplicated_lines_density) or 0) + max(0.0, 80.0 - float(_safe_number(row.coverage) or 80))


@router.get("/recruiter/candidate-insights/{run_id}", response_model=RecruiterCandidateInsightResponse)
async def get_recruiter_candidate_insights(
    run_id: int,
    force_refresh: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["recruiter"])),
):
    row = (
        db.query(AnalysisRun, Repository, SkillScore, RecruiterCandidate, SonarAnalysisSummary, RecruiterTask)
        .join(Repository, AnalysisRun.repository_id == Repository.id)
        .join(
            SkillScore,
            (SkillScore.analysis_run_id == AnalysisRun.id) & (SkillScore.user_id == current_user.id),
        )
        .join(RecruiterCandidate, RecruiterCandidate.analysis_run_id == AnalysisRun.id)
        .outerjoin(SonarAnalysisSummary, SonarAnalysisSummary.analysis_run_id == AnalysisRun.id)
        .outerjoin(RecruiterTask, RecruiterTask.id == RecruiterCandidate.task_id)
        .filter(
            AnalysisRun.id == run_id,
            AnalysisRun.user_id == current_user.id,
            SkillScore.user_id == current_user.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Candidate analysis not found")

    run, repo, score, candidate, sonar_summary, task = row
    if run.status != "completed":
        raise HTTPException(status_code=400, detail="Candidate analysis is not completed")
    if task and task.recruiter_id != current_user.id:
        raise HTTPException(status_code=404, detail="Candidate analysis not found")

    dashboard_row = build_candidate_dashboard_row(
        run,
        repo,
        score,
        candidate,
        sonar_summary,
        task,
        repo_count=1,
        contribution_count=1,
    )

    cached = get_cached_recruiter_candidate_insight(run)
    if cached and not force_refresh:
        return RecruiterCandidateInsightResponse(**_summary_candidate_from_row(dashboard_row, cached))

    sonar_issues = (
        db.query(SonarIssue)
        .filter(SonarIssue.analysis_run_id == run.id)
        .all()
    )
    sonar_issues = sorted(sonar_issues, key=lambda item: (_severity_rank(item.severity), item.file_path or "", item.line or 0))[:10]

    security_findings = (
        db.query(SecurityFinding)
        .filter(SecurityFinding.analysis_run_id == run.id)
        .all()
    )
    security_findings = sorted(security_findings, key=lambda item: (_severity_rank(item.severity), item.file_path or "", item.line_number or 0))[:10]

    file_measures = (
        db.query(SonarFileMeasure)
        .filter(SonarFileMeasure.analysis_run_id == run.id)
        .all()
    )
    risky_files = sorted(file_measures, key=_risky_file_rank, reverse=True)[:10]

    llm_payload = build_recruiter_candidate_llm_payload(
        dashboard_row,
        run,
        repo,
        candidate,
        task,
        sonar_issues,
        security_findings,
        risky_files,
    )

    ai_mode = (os.environ.get("AI_MODE") or "openrouter").lower()
    model_source = ai_mode if ai_mode in {"openrouter", "ollama"} else "openrouter"
    try:
        insight = generate_recruiter_candidate_insights(llm_payload)
    except Exception as exc:
        logger.warning("recruiter_candidate_insights failed; using fallback for run_id=%s: %s", run.id, exc)
        insight = _fallback_recruiter_candidate_insights(llm_payload)
        model_source = "fallback"

    cached_payload = set_cached_recruiter_candidate_insight(run, insight, model_source)
    db.commit()
    return RecruiterCandidateInsightResponse(**_summary_candidate_from_row(dashboard_row, cached_payload))


@router.delete("/recruiter/analysis/{analysis_id}")
@router.delete("/recruiter/candidates/{analysis_id}")
async def delete_recruiter_candidate_analysis(
    analysis_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["recruiter"])),
):
    run = (
        db.query(AnalysisRun)
        .filter(
            AnalysisRun.id == analysis_id,
            AnalysisRun.user_id == current_user.id,
        )
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    repo_analysis = (
        db.query(RepositoryAnalysis)
        .filter(
            RepositoryAnalysis.last_run_id == analysis_id,
            RepositoryAnalysis.user_id == current_user.id,
        )
        .first()
    )

    try:
        if repo_analysis:
            if repo_analysis.results_path and os.path.exists(repo_analysis.results_path):
                if os.path.isdir(repo_analysis.results_path):
                    import shutil
                    shutil.rmtree(repo_analysis.results_path)
                else:
                    os.remove(repo_analysis.results_path)
            db.delete(repo_analysis)

        (
            db.query(RecruiterCandidate)
            .filter(RecruiterCandidate.analysis_run_id == analysis_id)
            .delete(synchronize_session=False)
        )
        (
            db.query(CodeMetrics)
            .filter(CodeMetrics.analysis_run_id == analysis_id)
            .delete(synchronize_session=False)
        )
        (
            db.query(SecurityFinding)
            .filter(SecurityFinding.analysis_run_id == analysis_id)
            .delete(synchronize_session=False)
        )
        (
            db.query(SonarIssue)
            .filter(SonarIssue.analysis_run_id == analysis_id)
            .delete(synchronize_session=False)
        )
        (
            db.query(SonarFileMeasure)
            .filter(SonarFileMeasure.analysis_run_id == analysis_id)
            .delete(synchronize_session=False)
        )
        (
            db.query(SonarAnalysisSummary)
            .filter(SonarAnalysisSummary.analysis_run_id == analysis_id)
            .delete(synchronize_session=False)
        )
        (
            db.query(SkillScore)
            .filter(
                SkillScore.analysis_run_id == analysis_id,
                SkillScore.user_id == current_user.id,
            )
            .delete(synchronize_session=False)
        )
        db.delete(run)
        db.commit()
    except Exception:
        db.rollback()
        logging.exception(
            "Failed to delete recruiter candidate analysis run_id=%s user_id=%s",
            analysis_id,
            current_user.id,
        )
        raise HTTPException(status_code=500, detail="Failed to delete candidate analysis")

    return {
        "deleted": True,
        "analysis_id": analysis_id,
        "analysis_exists": False,
    }


@router.get("/{analysis_run_id}/detailed-metrics")
async def get_detailed_metrics_breakdown(
    analysis_run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.id == analysis_run_id)
        .first()
    )

    if not run or run.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    if run.status != "completed":
        raise HTTPException(status_code=400, detail="Analysis run is not completed")

    score_row = (
        db.query(SkillScore)
        .filter(
            SkillScore.analysis_run_id == run.id,
            SkillScore.user_id == current_user.id,
        )
        .first()
    )
    metric_rows = (
        db.query(CodeMetrics)
        .filter(CodeMetrics.analysis_run_id == run.id)
        .all()
    )
    findings = (
        db.query(SecurityFinding)
        .filter(SecurityFinding.analysis_run_id == run.id)
        .all()
    )

    total_files = len(metric_rows)
    total_loc = 0
    cyclomatic_values: list[float] = []
    duplication_values: list[float] = []
    maintainability_index_values: list[float] = []
    docstring_coverage_values: list[float] = []
    test_ratio_values: list[float] = []
    avg_nesting_values: list[float] = []
    function_size_values: list[float] = []
    comment_ratio_values: list[float] = []

    style_violations_total = 0
    missing_docstrings_total = 0
    long_functions_total = 0
    deep_nesting_total = 0
    too_many_params_total = 0
    unused_variables_total = 0
    import_coupling_total = 0
    test_files_total = 0
    max_inheritance_depth = 0

    for row in metric_rows:
        raw = row.raw_metrics if isinstance(row.raw_metrics, dict) else {}

        loc = row.lines_of_code if row.lines_of_code is not None else safe_int(raw.get("loc"), 0)
        total_loc += loc

        cyclomatic = (
            row.cyclomatic_complexity
            if row.cyclomatic_complexity is not None
            else safe_float(raw.get("cyclomatic_complexity"), 0.0)
        )
        cyclomatic_values.append(cyclomatic)

        duplication = (
            row.duplication_score
            if row.duplication_score is not None
            else safe_float(raw.get("duplication_score"), 0.0)
        )
        duplication_values.append(duplication)

        if row.maintainability_index is not None:
            maintainability_index_values.append(safe_float(row.maintainability_index, 0.0))

        if raw.get("docstring_coverage") is not None:
            docstring_coverage_values.append(safe_float(raw.get("docstring_coverage"), 0.0))
        if raw.get("test_function_ratio") is not None:
            test_ratio_values.append(safe_float(raw.get("test_function_ratio"), 0.0))
        if raw.get("avg_nesting_depth") is not None:
            avg_nesting_values.append(safe_float(raw.get("avg_nesting_depth"), 0.0))
        if raw.get("avg_function_size") is not None:
            function_size_values.append(safe_float(raw.get("avg_function_size"), 0.0))
        if raw.get("comment_ratio") is not None:
            comment_ratio_values.append(safe_float(raw.get("comment_ratio"), 0.0))

        style_violations_total += safe_int(raw.get("style_violations"), 0)
        missing_docstrings_total += safe_int(raw.get("missing_docstrings"), 0)
        long_functions_total += safe_int(raw.get("long_functions"), 0)
        deep_nesting_total += safe_int(raw.get("deep_nesting"), 0)
        too_many_params_total += safe_int(raw.get("too_many_params"), 0)
        unused_variables_total += safe_int(raw.get("unused_variables"), 0)
        import_coupling_total += safe_int(raw.get("import_coupling"), 0)

        if bool(raw.get("is_test_file")):
            test_files_total += 1

        max_inheritance_depth = max(
            max_inheritance_depth,
            safe_int(raw.get("max_inheritance_depth"), 0),
        )

    findings_by_severity = Counter(normalize_severity(f.severity) for f in findings)
    findings_by_owasp = Counter((f.owasp_category or "Unknown") for f in findings)
    findings_by_file = Counter(
        (os.path.basename((f.file_path or "unknown").replace("\\", "/")) or "unknown")
        for f in findings
    )

    def _avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    total_loc = sum(row.lines_of_code or 0 for row in metric_rows)

    security_score_inputs = [
        {
            "severity": f.severity,
            "cwe": f.cwe,
            "file_path": f.file_path,
            "tool": f.tool,
        }
        for f in findings
    ]
    security_breakdown = compute_security_score_breakdown(security_score_inputs, total_loc)
    security_score = security_breakdown["overall"]
    sonar_summary = build_sonar_repo_summary(run)
    sonar_health_score = sonar_summary["sonar_health_score"]
    skill_fields = _skill_score_fields(
        score_row,
        sonar_health_score=sonar_health_score,
        security_score=security_score,
    )

    ai_insights = run.ai_insights or {}
    if isinstance(ai_insights, dict):
        ai_insights = dict(ai_insights)
        ai_insights.pop("final_categorized_findings", None)
        ai_insights = _without_removed_skill_score_outputs(ai_insights)

    analysis_context = await build_personal_repo_context(
        db,
        current_user,
        run.repository,
        run.branch,
    )

    return {
        "analysis_run_id": run.id,
        "repo": run.repository.full_name,
        "branch": run.branch,
        "status": run.status,
        "analysis_context": analysis_context,
        "scores": {
            **skill_fields,
            "sonar_health_score": sonar_health_score,
            "sonar_state": sonar_summary["sonar_state"],
            "quality_gate": sonar_summary["quality_gate"],
            "security_score": round(security_score, 2),
            "security_score_breakdown": security_breakdown,
        },
        "detailed_metrics": {
            "repository_static_metrics": {
                "python_files": total_files,
                "total_loc": total_loc,
                "avg_cyclomatic_complexity": _avg(cyclomatic_values),
                "avg_duplication_score": _avg(duplication_values),
                "style_violations": style_violations_total,
                "unused_variables": unused_variables_total,
                "avg_docstring_coverage": _avg(docstring_coverage_values),
                "missing_docstrings": missing_docstrings_total,
                "avg_maintainability_index": _avg(maintainability_index_values),
                "avg_comment_ratio": _avg(comment_ratio_values),
                "long_functions": long_functions_total,
                "too_many_params": too_many_params_total,
                "test_files": test_files_total,
                "avg_test_function_ratio": _avg(test_ratio_values),
            },
        },
        "security": {
            "findings_count": len(findings),
            "severity_distribution": {
                "HIGH": findings_by_severity.get("HIGH", 0),
                "MEDIUM": findings_by_severity.get("MEDIUM", 0),
                "LOW": findings_by_severity.get("LOW", 0),
            },
            "owasp_distribution": dict(findings_by_owasp),
            "top_vulnerable_files": dict(findings_by_file.most_common(5)),
        },
        "completed_at": run.completed_at,
        "ai_insights": ai_insights,
    }


@router.get("/{analysis_run_id}/learning-recommendations")
async def get_learning_recommendations(
    analysis_run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.id == analysis_run_id)
        .first()
    )

    if not run or run.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    if run.status != "completed":
        raise HTTPException(status_code=400, detail="Analysis run is not completed")

    score_row = (
        db.query(SkillScore)
        .filter(
            SkillScore.analysis_run_id == run.id,
            SkillScore.user_id == current_user.id,
        )
        .first()
    )

    metric_rows = db.query(CodeMetrics).filter(CodeMetrics.analysis_run_id == run.id).all()
    findings = db.query(SecurityFinding).filter(SecurityFinding.analysis_run_id == run.id).all()
    sonar_summary_row = (
        db.query(SonarAnalysisSummary)
        .filter(SonarAnalysisSummary.analysis_run_id == run.id)
        .first()
    )
    sonar_issue_rows = db.query(SonarIssue).filter(SonarIssue.analysis_run_id == run.id).all()
    sonar_file_measure_rows = (
        db.query(SonarFileMeasure)
        .filter(SonarFileMeasure.analysis_run_id == run.id)
        .all()
    )

    ai_insights = run.ai_insights or {}
    if not isinstance(ai_insights, dict):
        ai_insights = {}

    detected_skill_gaps = []
    llm_skill_gaps = ai_insights.get("llm_skill_gaps") or {}
    if isinstance(llm_skill_gaps, dict) and isinstance(llm_skill_gaps.get("skill_gaps"), list):
        detected_skill_gaps = [
            gap for gap in llm_skill_gaps.get("skill_gaps") or []
            if isinstance(gap, dict)
        ]

    cached = ai_insights.get("learning_recommendations")
    if _is_current_learning_recommendations(cached):
        return cached

    sonar_metrics = _sonar_metrics_for_learning(run, sonar_summary_row, sonar_file_measure_rows)
    try:
        payload = build_learning_recommendations(
            run,
            score_row,
            metric_rows,
            findings,
            sonar_metrics=sonar_metrics,
            sonar_issues=sonar_issue_rows,
            detected_skill_gaps=detected_skill_gaps,
        )
    except Exception as exc:
        logger.exception("[run=%s] Learning recommendations generation failed", run.id)
        payload = _empty_learning_recommendations_response(run)

    ai_insights["learning_recommendations"] = payload
    run.ai_insights = ai_insights
    db.commit()

    return payload


class UpdateProfileRequest(BaseModel):
    organization: Optional[str] = None
    job_title: Optional[str] = None


@router.patch("/profile")
async def update_profile(
    data: UpdateProfileRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if data.organization is not None:
        current_user.organization = data.organization.strip()
    if data.job_title is not None:
        current_user.job_title = data.job_title.strip()

    db.commit()
    db.refresh(current_user)

    return {
        "organization": current_user.organization,
        "job_title":    current_user.job_title,
    }

@router.get("/profile-dashboard")
async def get_profile_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Aggregated profile dashboard for the current developer.

    Returns:
      user            – profile info
      integrations    – connected services
      progress_overview – overall/best/most-improved/focus stats
      skill_timeline  – per-analysis score history (for the line chart)
      recent_improvements – latest skill deltas
      recent_activity – latest analysis runs & commits
      settings        – placeholder links
    """

    # ── 1. Fetch all completed SkillScore rows for this user 
    rows = (
        db.query(SkillScore, AnalysisRun, Repository)
        .join(AnalysisRun, SkillScore.analysis_run_id == AnalysisRun.id)
        .join(Repository,  AnalysisRun.repository_id  == Repository.id)
        .filter(
            SkillScore.user_id == current_user.id,
            AnalysisRun.user_id == current_user.id,
            AnalysisRun.status == "completed",
        )
        .order_by(AnalysisRun.completed_at.asc())   # asc for timeline
        .all()
    )

    # ── 2. User block ─────────────────────────────────────────────────────────
    github_login = None
    if current_user.github_access_token:
        try:
            _, github_login = await resolve_github_identity(db, current_user)
        except Exception:
            pass

    user_block = {
        "id":           current_user.id,
        "full_name":    current_user.full_name,
        "username":     current_user.username,
        "email":        current_user.work_email,
        "role":         current_user.role.value if current_user.role else None,
        "avatar_url":   current_user.avatar_url,
        "github_login": github_login,
        "member_since": current_user.created_at.isoformat() if current_user.created_at else None,
       
        "organization": current_user.organization,
        "job_title":    current_user.job_title,
        
    }

    
    integrations_block = {
        "github": {
            "connected": bool(current_user.github_access_token),
            "login":     github_login,
        },
    }

    # ── 4. Skill timeline 
    run_ids = [run.id for _, run, _ in rows]
    security_counts_by_run = {}
    if run_ids:
        security_counts_by_run = dict(
            db.query(SecurityFinding.analysis_run_id, func.count(SecurityFinding.id))
            .filter(SecurityFinding.analysis_run_id.in_(run_ids))
            .group_by(SecurityFinding.analysis_run_id)
            .all()
        )

    sonar_timeline = []
    analysis_records = []
    for skill_score, run, repo in rows:
        sonar_summary = build_sonar_repo_summary(run)
        sonar_payload = get_sonar_payload(run)
        sonar_measures = get_sonar_measure_map(sonar_payload)
        complexity = _safe_number(sonar_measures.get("complexity")) if sonar_payload else None
        health_score = _safe_number(sonar_summary["sonar_health_score"])
        security_score = _safe_number(skill_score.security_awareness_score)
        cognitive_complexity = _safe_number(sonar_summary["cognitive_complexity"])
        analysis_records.append({
            "month_key": _month_key(run.completed_at),
            "day_key": _day_key(run.completed_at),
            "health_score": health_score,
            "security_score": security_score,
            "bugs": _safe_number(sonar_summary["bugs"]),
            "code_smells": _safe_number(sonar_summary["code_smells"]),
            "coverage": _safe_number(sonar_summary["coverage"]),
            "duplication": _safe_number(sonar_summary["duplication_percentage"]),
            "complexity": complexity,
            "cognitive_complexity": cognitive_complexity,
            "complexity_for_reporting": complexity if complexity is not None else cognitive_complexity,
            "reliability": sonar_summary["reliability_rating"],
            "maintainability": sonar_summary["maintainability_rating"],
            "security_findings": int(security_counts_by_run.get(run.id, 0)),
        })
        skill_fields = _skill_score_fields(
            skill_score,
            sonar_health_score=sonar_summary["sonar_health_score"],
            security_score=skill_score.security_awareness_score,
        )
        sonar_timeline.append({
            "date":            run.completed_at.isoformat() if run.completed_at else None,
            "analysis_id":     run.id,
            "repo_name":       repo.name,
            **skill_fields,
            "security_score": security_score,
            "sonar_health_score": sonar_summary["sonar_health_score"],
            "quality_gate": sonar_summary["quality_gate"],
            "bugs": sonar_summary["bugs"],
            "code_smells": sonar_summary["code_smells"],
            "coverage": sonar_summary["coverage"],
            "duplication_percentage": sonar_summary["duplication_percentage"],
            "cognitive_complexity": sonar_summary["cognitive_complexity"],
            "complexity": complexity,
            "reliability_rating": sonar_summary["reliability_rating"],
            "maintainability_rating": sonar_summary["maintainability_rating"],
        })

    # ── 5. Progress overview 
    monthly_groups = defaultdict(list)
    for record in analysis_records:
        if record["month_key"]:
            monthly_groups[record["month_key"]].append(record)

    month_keys = sorted(monthly_groups.keys())
    include_year = len({key[:4] for key in month_keys}) > 1
    monthly_health_by_key = {
        key: _avg_present([item["health_score"] for item in values])
        for key, values in monthly_groups.items()
    }
    monthly_security_by_key = {
        key: _avg_present([item["security_score"] for item in values])
        for key, values in monthly_groups.items()
    }

    monthly_trends = [
        {
            "month": _month_label(key, include_year),
            "health_score": monthly_health_by_key.get(key),
            "security_score": monthly_security_by_key.get(key),
        }
        for key in month_keys
    ]

    metrics_breakdown = [
        {
            "month": _month_label(key, include_year),
            "duplication": _avg_present([item["duplication"] for item in values]),
            "reliability": _most_common_or_latest([item["reliability"] for item in values]),
            "maintainability": _most_common_or_latest([item["maintainability"] for item in values]),
            "coverage": _avg_present([item["coverage"] for item in values]),
            "complexity": _avg_present([item["complexity_for_reporting"] for item in values]),
        }
        for key, values in sorted(monthly_groups.items())
    ]

    daily_groups = defaultdict(list)
    for record in analysis_records:
        if record.get("day_key"):
            daily_groups[record["day_key"]].append(record)

    daily_trends_by_month = defaultdict(list)
    for day_key, values in sorted(daily_groups.items()):
        month_key = day_key[:7]
        daily_trends_by_month[month_key].append({
            "date": day_key,
            "day": _day_label(day_key),
            "health_score": _avg_present([item["health_score"] for item in values]),
            "security_score": _avg_present([item["security_score"] for item in values]),
        })

    daily_trends = [
        {
            "month_key": key,
            "month": _month_label(key, include_year),
            "days": days,
        }
        for key, days in sorted(daily_trends_by_month.items())
    ]

    now = datetime.now(timezone.utc)
    current_month_key = now.strftime("%Y-%m")
    previous_year = now.year if now.month > 1 else now.year - 1
    previous_month = now.month - 1 if now.month > 1 else 12
    previous_month_key = f"{previous_year:04d}-{previous_month:02d}"

    def _monthly_delta(values_by_key: dict[str, float | None]) -> float | None:
        current_value = values_by_key.get(current_month_key)
        previous_value = values_by_key.get(previous_month_key)
        if current_value is None or previous_value is None:
            return None
        return round(float(current_value) - float(previous_value), 2)

    avg_health_score = _avg_present([item["health_score"] for item in analysis_records])
    avg_security_score = _avg_present([item["security_score"] for item in analysis_records])
    score_overview = {
        "health_score": avg_health_score,
        "health_status": _health_status(avg_health_score),
        "security_score": avg_security_score,
        "security_status": _security_status(avg_security_score),
        "analysis_count": len([
            item for item in analysis_records
            if item["health_score"] is not None or item["security_score"] is not None
        ]),
        "monthly_health_delta": _monthly_delta(monthly_health_by_key),
        "monthly_security_delta": _monthly_delta(monthly_security_by_key),
    }

    avg_coverage = _avg_present([item["coverage"] for item in analysis_records])
    avg_duplication = _avg_present([item["duplication"] for item in analysis_records])
    avg_complexity = _avg_present([item["complexity"] for item in analysis_records])
    avg_cognitive_complexity = _avg_present([item["cognitive_complexity"] for item in analysis_records])
    avg_complexity_for_rules = avg_complexity if avg_complexity is not None else avg_cognitive_complexity
    avg_code_smells = _avg_present([item["code_smells"] for item in analysis_records])
    avg_bugs = _avg_present([item["bugs"] for item in analysis_records])
    reliability_rating = _most_common_or_latest([item["reliability"] for item in analysis_records])
    maintainability_rating = _most_common_or_latest([item["maintainability"] for item in analysis_records])

    def _rating_contribution(label: str | None, points: dict[str, int], fallback: int) -> int:
        return points.get(label or "", fallback)

    component_contribution = []
    if maintainability_rating:
        value = _rating_contribution(maintainability_rating, {"A": 25, "B": 18, "C": 8, "D": -8, "E": -14}, -6)
        component_contribution.append({"name": "Maintainability", "value": value, "type": "positive" if value >= 0 else "negative"})
    if avg_coverage is not None:
        value = 20 if avg_coverage >= 80 else 10 if avg_coverage >= 50 else -12
        component_contribution.append({"name": "Test Coverage", "value": value, "type": "positive" if value >= 0 else "negative"})
    if reliability_rating:
        value = _rating_contribution(reliability_rating, {"A": 18, "B": 12, "C": 6, "D": -8, "E": -14}, -6)
        component_contribution.append({"name": "Reliability", "value": value, "type": "positive" if value >= 0 else "negative"})
    if avg_complexity_for_rules is not None:
        value = -10 if avg_complexity_for_rules > 40 else -6 if avg_complexity_for_rules >= 25 else 8
        component_contribution.append({"name": "Complexity", "value": value, "type": "positive" if value >= 0 else "negative"})
    if avg_duplication is not None:
        value = -8 if avg_duplication > 10 else -4 if avg_duplication > 5 else 8
        component_contribution.append({"name": "Duplication", "value": value, "type": "positive" if value >= 0 else "negative"})
    if avg_bugs is not None:
        value = -12 if avg_bugs > 5 else -6 if avg_bugs >= 1 else 6
        component_contribution.append({"name": "Bugs", "value": value, "type": "positive" if value >= 0 else "negative"})
    if avg_code_smells is not None:
        value = -10 if avg_code_smells > 50 else -5 if avg_code_smells >= 20 else 6
        component_contribution.append({"name": "Code Smells", "value": value, "type": "positive" if value >= 0 else "negative"})

    # Recommended Skill Improvements repository selector
    # Build this list from the latest completed analysis runs for the current
    # developer, including repositories even when no LLM skill gaps exist.
    completed_runs = (
        db.query(AnalysisRun, Repository)
        .join(Repository, AnalysisRun.repository_id == Repository.id)
        .filter(
            AnalysisRun.user_id == current_user.id,
            AnalysisRun.status == "completed",
        )
        .order_by(
            AnalysisRun.completed_at.desc().nullslast(),
            AnalysisRun.triggered_at.desc().nullslast(),
        )
        .all()
    )

    latest_by_repo = {}
    for run, repo in completed_runs:
        if repo.id in latest_by_repo:
            continue

        ai_insights = run.ai_insights or {}
        skill_gaps = []
        if isinstance(ai_insights, dict):
            llm_skill_gaps = ai_insights.get("llm_skill_gaps") or {}
            if isinstance(llm_skill_gaps, dict):
                raw_gaps = llm_skill_gaps.get("skill_gaps")
                if isinstance(raw_gaps, list):
                    skill_gaps = raw_gaps

        latest_by_repo[repo.id] = {
            "repo_id": repo.id,
            "repo_name": repo.name,
            "repo_full_name": repo.full_name,
            "analysis_run_id": run.id,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "skill_gaps": skill_gaps,
        }

        if len(latest_by_repo) >= 10:
            break

    skill_gap_repositories = list(latest_by_repo.values())

    ready_timeline = [item for item in sonar_timeline if item.get("skill_score") is not None]
    if not ready_timeline:
        progress_overview = {
            "skill_score": None,
            "skill_score_level": "Unavailable",
            "skill_score_delta": None,
            "sonar_health_score": None,
            "sonar_state": "sonar_unavailable",
            "sonar_delta": None,
            "quality_gate": None,
        }
        recent_improvements = []
    else:
        latest = ready_timeline[-1]
        previous = ready_timeline[-2] if len(ready_timeline) > 1 else None
        latest_score = float(latest["skill_score"])
        previous_score = float(previous["skill_score"]) if previous else None
        latest_sonar = latest.get("sonar_health_score")
        previous_sonar = previous.get("sonar_health_score") if previous else None

        progress_overview = {
            "skill_score": round(latest_score, 2),
            "skill_score_level": latest.get("skill_score_level", "Unavailable"),
            "skill_score_delta": round(latest_score - previous_score, 2) if previous_score is not None else None,
            "sonar_health_score": latest_sonar,
            "sonar_state": "ready",
            "sonar_delta": (
                round(float(latest_sonar) - float(previous_sonar), 2)
                if latest_sonar is not None and previous_sonar is not None
                else None
            ),
            "quality_gate": latest.get("quality_gate"),
        }

        recent_improvements = [
            {
                "metric": "Skill Score",
                "score": round(latest_score, 1),
                "previous": round(previous_score, 1) if previous_score is not None else None,
                "delta": round(latest_score - previous_score, 2) if previous_score is not None else None,
            }
        ]

    # ── 6. Recent activity
    recent_runs = (
        db.query(AnalysisRun, Repository)
        .join(Repository, AnalysisRun.repository_id == Repository.id)
        .filter(AnalysisRun.user_id == current_user.id)
        .order_by(AnalysisRun.triggered_at.desc())
        .limit(10)
        .all()
    )

    recent_activity = []
    for run, repo in recent_runs:
        score_row = (
            db.query(SkillScore)
            .filter(
                SkillScore.analysis_run_id == run.id,
                SkillScore.user_id         == current_user.id,
            )
            .first()
        )
        sonar_summary = build_sonar_repo_summary(run)
        skill_fields = _skill_score_fields(
            score_row,
            sonar_health_score=sonar_summary["sonar_health_score"],
            security_score=getattr(score_row, "security_awareness_score", None),
        )
        recent_activity.append({
            "type":        "repository_analyzed",
            "repo_name":   repo.name,
            "full_name":   repo.full_name,
            "branch":      run.branch,
            "status":      run.status,
            "triggered_at": run.triggered_at.isoformat() if run.triggered_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            **skill_fields,
            "sonar_health_score": sonar_summary["sonar_health_score"],
            "sonar_state": sonar_summary["sonar_state"],
            "quality_gate": sonar_summary["quality_gate"],
            "analysis_id": run.id,
        })

    # ── 7. Settings 
    settings_block = {
        "account_settings":         "/settings/account",
        "connected_repositories":   "/settings/repositories",
        
    }

    return {
        "user":                 user_block,
        "integrations":         integrations_block,
        "progress_overview":    progress_overview,
        "score_overview":       score_overview,
        "monthly_trends":       monthly_trends,
        "daily_trends":         daily_trends,
        "metrics_breakdown":    metrics_breakdown,
        "component_contribution": component_contribution,
        "skill_gap_repositories": skill_gap_repositories,
        "sonar_timeline":       sonar_timeline,
        "recent_improvements":  recent_improvements,
        "recent_activity":      recent_activity,
        "settings":             settings_block,
    }


@router.get("/{analysis_run_id}/sonar-dashboard")
async def get_sonar_dashboard(
    analysis_run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.id == analysis_run_id)
        .first()
    )

    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    is_owner = run.user_id == current_user.id
    if not is_owner and not score_belongs_to_user(db, run.id, current_user.id):
        raise HTTPException(status_code=404, detail="Analysis run not found")

    if run.status != "completed":
        raise HTTPException(status_code=400, detail="Analysis run is not completed")

    return build_sonar_dashboard_payload(run, db)


@router.get("/{analysis_run_id}/sonar-results")
async def get_sonar_results(
    analysis_run_id: int,
    include_raw: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """This endpoint exposes SonarQube contribution-scoped analysis results from Sonar-specific tables. It intentionally does not use CodeMetrics."""
    run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.id == analysis_run_id)
        .first()
    )

    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    is_owner = run.user_id == current_user.id
    if not is_owner and not score_belongs_to_user(db, run.id, current_user.id):
        raise HTTPException(status_code=404, detail="Analysis run not found")

    score_row = (
        db.query(SkillScore)
        .filter(
            SkillScore.analysis_run_id == run.id,
            SkillScore.user_id == current_user.id,
        )
        .first()
    )
    summary = (
        db.query(SonarAnalysisSummary)
        .filter(SonarAnalysisSummary.analysis_run_id == run.id)
        .first()
    )
    file_rows = (
        db.query(SonarFileMeasure)
        .filter(SonarFileMeasure.analysis_run_id == run.id)
        .order_by(SonarFileMeasure.file_path.asc())
        .all()
    )
    issue_rows = (
        db.query(SonarIssue)
        .filter(SonarIssue.analysis_run_id == run.id)
        .filter(or_(SonarIssue.status.is_(None), func.upper(SonarIssue.status) != "CLOSED"))
        .order_by(SonarIssue.severity.asc(), SonarIssue.file_path.asc())
        .all()
    )

    base_payload = {
        "analysis_run_id": run.id,
        "repo": run.repository.full_name if run.repository else None,
        "branch": run.branch,
        "analysis_scope": run.analysis_scope,
        "status": run.status,
        "completed_at": run.completed_at,
        **_skill_score_fields(
            score_row,
            sonar_health_score=summary.sonar_health_score if summary else None,
            security_score=getattr(score_row, "security_awareness_score", None),
        ),
    }

    if not summary:
        return {
            **base_payload,
            "sonar": {
                "available": False,
                "reason": "sonar_results_not_found",
            },
            "files": [],
            "issues": [],
            "summary": {
                "files_count": 0,
                "issues_count": 0,
                "bugs_count": 0,
                "code_smells_count": 0,
            },
        }

    files = [
        {
            "file_path": row.file_path,
            "measures": _numeric_measure_map(row.measures),
            "coverage": _safe_number(row.coverage),
            "duplicated_lines": _safe_number(row.duplicated_lines),
            "duplicated_lines_density": _safe_number(row.duplicated_lines_density),
            "ncloc": _safe_number(row.ncloc),
            "complexity": _safe_number(row.complexity),
            "cognitive_complexity": _safe_number(row.cognitive_complexity),
            "functions": _safe_number(row.functions),
            "classes": _safe_number(row.classes),
            "statements": _safe_number(row.statements),
        }
        for row in file_rows
    ]
    issues = [
        {
            "issue_key": row.issue_key,
            "file_path": row.file_path,
            "line": row.line,
            "type": row.type,
            "severity": row.severity,
            "rule": row.rule,
            "message": row.message,
            "status": row.status,
            **({"raw_issue": row.raw_issue} if include_raw else {}),
        }
        for row in issue_rows
    ]
    issue_counts = _count_issues_by_type(issue_rows)
    sonar_block = {
        "available": True,
        "project_key": summary.project_key,
        "quality_gate": summary.quality_gate,
        "sonar_health_score": _safe_number(summary.sonar_health_score),
        "measures": _numeric_measure_map(summary.measures),
        "coverage": summary.coverage if isinstance(summary.coverage, dict) else {},
    }
    if include_raw:
        sonar_block["raw_payload"] = summary.raw_payload

    return {
        **base_payload,
        "sonar": sonar_block,
        "files": files,
        "issues": issues,
        "summary": {
            "files_count": len(files),
            "issues_count": len(issues),
            "bugs_count": issue_counts["BUG"],
            "code_smells_count": issue_counts["CODE_SMELL"],
        },
    }


@router.get("/{analysis_id}")
async def get_analysis_result(
    analysis_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.id == analysis_id)
        .first()
    )

    # if not run or (run.status == "completed" and not score_belongs_to_user(db, run.id, current_user.id)) or (run.status != "completed" and run.user_id != current_user.id):
    #     return {
    #         "analysis_id": analysis_id,
    #         "status": "pending",
    #     }
    if not run:
        return {"analysis_id": analysis_id, "status": "pending"}

    is_owner = run.user_id == current_user.id

    if not is_owner:
        return {"analysis_id": analysis_id, "status": "pending"}

    if run.status != "completed":
        return {
            "analysis_id": run.id,
            "status": run.status,
            "error_reason": (run.ai_insights or {}).get("error_reason"),
            "message": "Analysis is still processing or failed."
        }

    score_row = db.query(SkillScore).filter(
        SkillScore.analysis_run_id == run.id,
        SkillScore.user_id == current_user.id,
    ).first()
    candidate = (
        db.query(RecruiterCandidate)
        .filter(RecruiterCandidate.analysis_run_id == run.id)
        .first()
    )
    ai_insights = run.ai_insights or {}
    if isinstance(ai_insights, dict):
        ai_insights = dict(ai_insights)
        ai_insights.pop("final_categorized_findings", None)
        ai_insights = _without_removed_skill_score_outputs(ai_insights)

    sonar_summary = build_sonar_repo_summary(run)
    skill_fields = _skill_score_fields(
        score_row,
        sonar_health_score=sonar_summary["sonar_health_score"],
        security_score=getattr(score_row, "security_awareness_score", None),
    )
    security_assessment = _security_breakdown_for_run(
        db,
        run.id,
        getattr(score_row, "security_awareness_score", None),
    )
    return {
        "analysis_run_id": run.id,
        "repo": run.repository.full_name,
        "branch": run.branch,
        "status": run.status,
        "candidate_name": candidate.candidate_name if candidate else None,
        "github_login": candidate.github_login if candidate else None,
        "github_avatar_url": candidate.github_avatar_url if candidate else None,
        **skill_fields,
        "sonar_health_score": sonar_summary["sonar_health_score"],
        "sonar_state": sonar_summary["sonar_state"],
        "quality_gate": sonar_summary["quality_gate"],
        "bugs": sonar_summary["bugs"],
        "code_smells": sonar_summary["code_smells"],
        "coverage": sonar_summary["coverage"],
        "duplication_percentage": sonar_summary["duplication_percentage"],
        "cognitive_complexity": sonar_summary["cognitive_complexity"],
        "reliability_rating": sonar_summary["reliability_rating"],
        "maintainability_rating": sonar_summary["maintainability_rating"],
        "technical_debt_minutes": sonar_summary["technical_debt_minutes"],
        "lines_of_code": sonar_summary["lines_of_code"],
        "security_findings_count": security_assessment["findings_count"],
        "security_assessment": security_assessment,
        "ai_insights": ai_insights,
        "completed_at": run.completed_at
    }
    

@router.get("/skills/summary")
async def get_skills_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns the latest SonarQube health summary across completed analysis
    runs for the current user, plus a list of completed repos (with their
    latest analysis_run_id) to populate the repository dropdown.

    Response shape:
    {
        "sonar_health_score": float | None,
        "sonar_state": str,
        "delta": float | None,
        "sonar_metrics": dict,
        "repos": [
            {
                "analysis_id": int,
                "repo_name":   str,
                "full_name":   str,
                "branch":      str,
                "sonar_health_score": float | None,
                "quality_gate": str | None,
                "completed_at": str,
            }, ...
        ]
    }
    """

    # 1. Pull all completed skill score rows for this user, newest first
    # Temporary diagnostic — remove after confirming fix
    all_runs_count = (
        db.query(SkillScore)
        .join(AnalysisRun, SkillScore.analysis_run_id == AnalysisRun.id)
        .filter(
            SkillScore.user_id == current_user.id,
            AnalysisRun.user_id == current_user.id,
        )
        .count()
    )
    logging.info(
        "[user=%s] Total SkillScore rows before scope filter: %s",
        current_user.id,
        all_runs_count,
    )

    score_rows = (
        db.query(SkillScore, AnalysisRun, Repository)
        .join(AnalysisRun, SkillScore.analysis_run_id == AnalysisRun.id)
        .join(Repository,  AnalysisRun.repository_id == Repository.id)
        .filter(
            SkillScore.user_id    == current_user.id,
            AnalysisRun.user_id   == current_user.id,
            AnalysisRun.status    == "completed",
        )
        .order_by(AnalysisRun.triggered_at.desc())
    )
    if current_user.role.value == "developer":
        score_rows = score_rows.filter(AnalysisRun.analysis_scope == "contribution")
    logging.info(
        "[user=%s] SkillScore rows after scope filter: %s",
        current_user.id,
        len(score_rows.all()),
    )
    score_rows = score_rows.all()

    if not score_rows:
        empty_context = {
            "has_github_identity": bool(current_user.github_access_token),
            "github_login": None,
        }
        if current_user.github_access_token:
            try:
                _, github_login = await resolve_github_identity(db, current_user)
                empty_context["has_github_identity"] = bool(github_login)
                empty_context["github_login"] = github_login
            except Exception:
                pass

        return {
            "skill_score": None,
            "skill_score_level": "Unavailable",
            "skill_score_delta": None,
            "sonar_health_score": None,
            "sonar_state": "sonar_unavailable",
            "delta": None,
            "sonar_metrics": {},
            "repos": [],
            "viewer": empty_context,
        }

    # 2. Build analysis list. Keep each run visible so users can inspect
    # older contribution snapshots or disconnect only one instance.
    repos_list: list[dict] = []
    for skill_score, run, repo in score_rows:
        context = await build_personal_repo_context(db, current_user, repo, run.branch)
        sonar_summary = build_sonar_repo_summary(run)
        skill_fields = _skill_score_fields(
            skill_score,
            sonar_health_score=sonar_summary["sonar_health_score"],
            security_score=skill_score.security_awareness_score,
        )
        repos_list.append({
            "analysis_id":  run.id,
            "repo_name":    repo.name,
            "full_name":    repo.full_name,
            "branch":       run.branch,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "is_private":   bool(repo.is_private),
            "analysis_context": context,
            "contributor_login": run.contributor_login,
            **sonar_summary,
            **skill_fields,
        })

    ready_repos = [repo for repo in repos_list if repo.get("skill_score") is not None]
    latest_score = ready_repos[0]["skill_score"] if ready_repos else None
    previous_score = ready_repos[1]["skill_score"] if len(ready_repos) > 1 else None
    skill_score_delta = round(float(latest_score) - float(previous_score), 2) if latest_score is not None and previous_score is not None else None
    latest_sonar_score = ready_repos[0]["sonar_health_score"] if ready_repos else None

    return {
        "skill_score": latest_score,
        "skill_score_level": ready_repos[0]["skill_score_level"] if ready_repos else "Unavailable",
        "skill_score_delta": skill_score_delta,
        "sonar_health_score": latest_sonar_score,
        "sonar_state": "ready" if latest_sonar_score is not None else "sonar_unavailable",
        "delta": skill_score_delta,
        "sonar_metrics": ready_repos[0] if ready_repos else {},
        "repos": repos_list,
        "viewer": {
            "has_github_identity": bool(repos_list[0]["analysis_context"].get("has_github_identity")) if repos_list else bool(current_user.github_access_token),
            "github_login": repos_list[0]["analysis_context"].get("github_login") if repos_list else None,
        },
    }
