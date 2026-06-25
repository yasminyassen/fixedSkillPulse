from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.auth_utils import require_role
from app.db.database import get_db
from app.db.models import (
    AnalysisRun,
    CodeMetrics,
    ContributorAnalysisSummary,
    Repository,
    SecurityFinding,
    SkillScore,
    SonarAnalysisSummary,
    SonarFileMeasure,
    SonarIssue,
    User,
    UserRole,
)
from app.services.security_service import normalize_severity
from app.services.sonarqube_score_service import classify_skill_score
from app.services.llm_client import generate_repository_manager_recommendations
from app.schemas.manager_schemas import (
    ManagerActionableRecommendations,
    ManagerDashboardContributorHighlight,
    ManagerDashboardContributorRow,
    ManagerDashboardMetricCard,
    ManagerDashboardOverview,
    ManagerDashboardOverviewTrendPoint,
    ManagerDashboardRepo,
    ManagerDashboardRecommendations,
    ManagerDashboardRepositorySummary,
    ManagerDashboardRiskGroups,
    ManagerDashboardRiskItem,
    ManagerDashboardTeamPerformance,
    ManagerKpis,
    ManagerMemberDetail,
    ManagerSkillDistribution,
    ManagerTeamInsights,
    ManagerTeamMember,
    ManagerTopPerformer,
    ManagerTrendPoint,
)
from ai_services.insights.ai_insights import generate_insights
from ai_services.rag.rag_seeder import STANDARDS_DOC_ID


router = APIRouter(prefix="/manager/dashboard", tags=["manager-dashboard"])


MANAGER_INSIGHT_STYLE_VERSION = "manager_action_recommendations_v2"
MEMBER_DETAIL_STYLE_VERSION = "manager_member_detail_v1"
RECOMMENDATION_BUCKET_KEYS = (
    "mandatory",
    "highly_required",
    "nice_to_have",
    "enhanced",
)
OVERVIEW_RECOMMENDATION_KEYS = (
    "fix_first",
    "prioritize_next",
    "plan_when_possible",
    "strengthen_further",
    "architectural_concerns",
    "delivery_risks",
    "quality_concerns",
    "team_strengths",
    "recommended_priorities",
)
DEFAULT_TREND_RANGE = "6m"

SONAR_METRIC_KEYS = (
    "sonar_health_score",
    "bugs",
    "code_smells",
    "coverage",
    "duplication_percentage",
    "cognitive_complexity",
)

MANAGER_DASHBOARD_PROMPT = (
    "CRITICAL: Rely STRICTLY on the numerical metrics provided in the payload. "
    "DO NOT invent, guess, or hallucinate numbers like file counts or scores. "
    "DO NOT mention or evaluate Security/Vulnerabilities at all. Focus only on "
    "Skill Score, SonarQube Health Score, Bugs, Code Smells, Coverage, Duplication, and Cognitive Complexity. "
    "Return ONLY valid JSON with exactly one top-level key: actionable_recommendations. "
    "actionable_recommendations must contain exactly these bucket keys: "
    "mandatory, highly_required, nice_to_have, enhanced. "
    "Each bucket is a list of manager-facing recommendation strings grounded in the metrics. "
    "mandatory = critical delivery or regression risk. "
    "highly_required = important velocity or quality issues. "
    "nice_to_have = low-risk polish when capacity allows. "
    "enhanced = strength-based leverage opportunities. "
    "Generate only genuinely relevant items; empty buckets are allowed."
)

MANAGER_MEMBER_DETAIL_PROMPT = (
    "You are advising an Engineering Manager about one developer on their team. "
    "Return ONLY valid JSON with exactly two keys: key_strengths and areas_for_improvement. "
    "Write to the manager, not to the developer. "
    "Use only the exact values provided in the payload. "
    "Discuss only Skill Score, SonarQube Health Score, Bugs, Code Smells, Coverage, Duplication, and Cognitive Complexity. "
    "Do NOT mention Security, Vulnerabilities, OWASP, or compliance. "
    "Each item must cite at least one exact metric from the payload."
)

ScoreRow = tuple[ContributorAnalysisSummary, AnalysisRun, Repository, User]


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _round_score(value: float) -> float:
    return round(value, 2)


def _avg(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        return 0.0
    return sum(values) / len(values)


def _model_to_dict(model: object) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _run_time(run: AnalysisRun) -> datetime:
    value = run.completed_at or run.triggered_at or datetime.min.replace(tzinfo=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _normalise_trend_range(range_value: str | None) -> str:
    value = (range_value or DEFAULT_TREND_RANGE).strip().lower()
    if value == "1y":
        value = "12m"
    allowed = {"30d", "90d", "6m", "12m", "all"}
    if value not in allowed:
        return DEFAULT_TREND_RANGE
    return value


def _trend_range_start(range_key: str, reference: datetime | None = None) -> datetime | None:
    if range_key == "all":
        return None
    now = reference or datetime.now(timezone.utc)
    offsets = {
        "30d": timedelta(days=30),
        "90d": timedelta(days=90),
        "6m": timedelta(days=183),
        "12m": timedelta(days=365),
    }
    return now - offsets[range_key]


def _filter_rows_by_trend_range(rows: list[ScoreRow], range_key: str) -> list[ScoreRow]:
    start = _trend_range_start(range_key)
    if start is None:
        return rows
    return [row for row in rows if _run_time(row[1]) >= start]


def _trend_group_key(run_time: datetime, range_key: str) -> tuple[str, str]:
    if range_key == "30d":
        return run_time.strftime("%Y-%m-%d"), run_time.strftime("%b %d")
    if range_key == "90d":
        iso = run_time.isocalendar()
        return f"{iso.year}-W{iso.week:02d}", f"Week {iso.week}"
    period = run_time.strftime("%Y-%m")
    return period, run_time.strftime("%b %Y")


def _contributor_summary_rows(
    db: Session,
    manager_id: int,
    repo_id: int | None = None,
) -> list[ScoreRow]:
    query = (
        db.query(ContributorAnalysisSummary, AnalysisRun, Repository, User)
        .join(AnalysisRun, ContributorAnalysisSummary.analysis_run_id == AnalysisRun.id)
        .join(Repository, AnalysisRun.repository_id == Repository.id)
        .join(User, ContributorAnalysisSummary.user_id == User.id)
        .filter(
            AnalysisRun.user_id == manager_id,
            AnalysisRun.status == "completed",
            AnalysisRun.analysis_scope == "team_contributions",
            User.role == UserRole.developer,
        )
    )
    if repo_id is not None:
        query = query.filter(AnalysisRun.repository_id == repo_id)

    return query.order_by(AnalysisRun.completed_at.asc(), AnalysisRun.triggered_at.asc()).all()


def _latest_contributor_summaries(
    db: Session,
    manager_id: int,
    repo_id: int | None = None,
) -> list[ScoreRow]:
    return _latest_contributor_score_rows(_contributor_summary_rows(db, manager_id, repo_id))


def _query_manager_score_rows(
    db: Session,
    manager_id: int,
    repo_id: int | None = None,
) -> list[ScoreRow]:
    return _contributor_summary_rows(db, manager_id, repo_id)


def _contributor_metric_payload_from_summary(summary: ContributorAnalysisSummary) -> dict:
    complexity = summary.cognitive_complexity if summary.cognitive_complexity is not None else summary.complexity
    return {
        "skill_score": _number_or_none(summary.skill_score),
        "sonar_health_score": _number_or_none(summary.sonar_health_score),
        "health_score": _number_or_none(summary.sonar_health_score),
        "security_score": _number_or_none(summary.security_score),
        "coverage": _number_or_none(summary.coverage),
        "bugs": _number_or_none(summary.bugs),
        "code_smells": _number_or_none(summary.code_smells),
        "complexity": _number_or_none(complexity),
        "cognitive_complexity": _number_or_none(complexity),
        "duplicated_lines": _number_or_none(summary.duplicated_lines),
        "duplication_percentage": _number_or_none(summary.duplicated_lines_density),
        "quality_gate": summary.quality_gate,
    }


def _avg_optional(values: Iterable[object]) -> float | None:
    valid = [float(value) for value in values if value is not None]
    if not valid:
        return None
    return _round_score(_avg(valid))


def _average_sonar_by_developer(rows: list[ScoreRow]) -> dict[int, dict[str, float | int | None]]:
    grouped: dict[int, dict[str, list[object]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        summary, _, _, user = row
        payload = _contributor_metric_payload_from_summary(summary)
        grouped[user.id]["skill_score"].append(payload.get("skill_score"))
        for key in SONAR_METRIC_KEYS:
            grouped[user.id][key].append(payload.get(key))
        grouped[user.id]["quality_gate_pass"].append(1.0 if payload.get("quality_gate") == "OK" else 0.0)

    return {
        user_id: {
            **{key: _avg_optional(values) for key, values in metric_groups.items() if key != "quality_gate_pass"},
            "quality_gate_pass_rate": _avg_optional(metric_groups.get("quality_gate_pass", [])),
        }
        for user_id, metric_groups in grouped.items()
    }


def _team_average_from_developer_averages(
    developer_averages: dict[int, dict[str, float | int | None]],
    key: str,
) -> float | None:
    return _avg_optional(scores.get(key) for scores in developer_averages.values())


def _analysis_run_ids(rows: list[ScoreRow]) -> list[int]:
    return sorted({run.id for _, run, _, _ in rows})


def _build_team_score_payload(rows: list[ScoreRow]) -> dict[str, float | int | None]:
    developer_averages = _average_sonar_by_developer(rows)
    return {
        "skill_score": _team_average_from_developer_averages(developer_averages, "skill_score"),
        "sonar_health_score": _team_average_from_developer_averages(developer_averages, "sonar_health_score"),
        "bugs": _team_average_from_developer_averages(developer_averages, "bugs"),
        "code_smells": _team_average_from_developer_averages(developer_averages, "code_smells"),
        "coverage": _team_average_from_developer_averages(developer_averages, "coverage"),
        "duplication_percentage": _team_average_from_developer_averages(developer_averages, "duplication_percentage"),
        "cognitive_complexity": _team_average_from_developer_averages(developer_averages, "cognitive_complexity"),
        "quality_gate_pass_rate": _team_average_from_developer_averages(developer_averages, "quality_gate_pass_rate"),
    }


def _build_team_aggregate_metrics(db: Session, run_ids: list[int]) -> dict:
    if not run_ids:
        return {
            "total_files_analyzed": 0,
            "test_files": 0,
            "avg_cyclomatic_complexity": 0.0,
            "long_functions": 0,
            "avg_docstring_coverage": 0.0,
            "import_coupling_total": 0,
            "style_violations": 0,
            "total_loc": 0,
            "avg_duplication_score": 0.0,
            "unused_variables": 0,
        }

    metric_rows = (
        db.query(CodeMetrics)
        .filter(CodeMetrics.analysis_run_id.in_(run_ids))
        .all()
    )

    total_loc = 0
    test_files = 0
    cyclomatic_values: list[float] = []
    docstring_values: list[float] = []
    duplication_values: list[float] = []
    test_ratio_values: list[float] = []
    function_size_values: list[float] = []
    nesting_values: list[float] = []
    maintainability_index_values: list[float] = []
    long_functions = 0
    import_coupling_total = 0
    style_violations = 0
    unused_variables = 0

    for row in metric_rows:
        raw = row.raw_metrics if isinstance(row.raw_metrics, dict) else {}
        total_loc += int(row.lines_of_code or raw.get("loc") or 0)
        cyclomatic_values.append(_safe_float(row.cyclomatic_complexity, _safe_float(raw.get("cyclomatic_complexity"))))
        duplication_values.append(_safe_float(row.duplication_score, _safe_float(raw.get("duplication_score"))))

        if raw.get("docstring_coverage") is not None:
            docstring_values.append(_safe_float(raw.get("docstring_coverage")))
        if raw.get("test_function_ratio") is not None:
            test_ratio_values.append(_safe_float(raw.get("test_function_ratio")))
        if raw.get("avg_function_size") is not None:
            function_size_values.append(_safe_float(raw.get("avg_function_size")))
        if raw.get("avg_nesting_depth") is not None:
            nesting_values.append(_safe_float(raw.get("avg_nesting_depth")))
        if row.maintainability_index is not None:
            maintainability_index_values.append(_safe_float(row.maintainability_index))
        if raw.get("is_test_file"):
            test_files += 1

        long_functions += int(raw.get("long_functions") or 0)
        import_coupling_total += int(raw.get("import_coupling") or raw.get("import_coupling_total") or 0)
        style_violations += int(raw.get("style_violations") or 0)
        unused_variables += int(raw.get("unused_variables") or 0)

    return {
        "total_files_analyzed": len(metric_rows),
        "test_files": test_files,
        "avg_cyclomatic_complexity": _round_score(_avg(cyclomatic_values)),
        "avg_test_function_ratio": _round_score(_avg(test_ratio_values)),
        "avg_function_size": _round_score(_avg(function_size_values)),
        "avg_nesting_depth": _round_score(_avg(nesting_values)),
        "avg_maintainability_index": _round_score(_avg(maintainability_index_values)),
        "long_functions": long_functions,
        "avg_docstring_coverage": _round_score(_avg(docstring_values)),
        "import_coupling_total": import_coupling_total,
        "style_violations": style_violations,
        "total_loc": total_loc,
        "avg_duplication_score": _round_score(_avg(duplication_values)),
        "unused_variables": unused_variables,
    }


def _empty_actionable_recommendations() -> ManagerActionableRecommendations:
    return ManagerActionableRecommendations()


def _normalise_recommendation_items(items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def _fallback_team_insights(scores: dict[str, float | int | None], metrics: dict) -> ManagerTeamInsights:
    recommendations = _empty_actionable_recommendations()
    test_files = int(metrics.get("test_files") or 0)
    total_files = int(metrics.get("total_files_analyzed") or 0)

    if test_files == 0 and total_files > 0:
        recommendations.mandatory.append(
            f"Zero test files across {total_files} analyzed files creates unmanaged regression risk; "
            "release confidence depends on manual verification."
        )

    doc_cov = metrics.get("avg_docstring_coverage")
    if doc_cov is not None and _safe_float(doc_cov) < 0.25 and total_files > 0:
        recommendations.highly_required.append(
            f"Docstring coverage at {_safe_float(doc_cov) * 100:.0f}% increases handoff friction and onboarding cost."
        )

    sonar_score = scores.get("sonar_health_score")
    if sonar_score is not None and float(sonar_score) >= 80.0:
        recommendations.enhanced.append(
            f"Sonar Health Score of {float(sonar_score):.0f}/100 indicates a leverage opportunity for expanded ownership."
        )
    elif sonar_score is not None and 0.0 < float(sonar_score) < 40.0:
        recommendations.mandatory.append(
            f"Sonar Health Score of {float(sonar_score):.0f}/100 is critically low and increases delivery risk."
        )

    bugs = scores.get("bugs")
    if bugs is not None and float(bugs) > 0:
        recommendations.highly_required.append(f"{float(bugs):.0f} SonarQube bugs should be triaged before expanding release scope.")

    coverage = scores.get("coverage")
    if coverage is not None and float(coverage) < 60:
        recommendations.highly_required.append(f"Coverage at {float(coverage):.1f}% leaves regression risk across the team baseline.")

    style_violations = int(metrics.get("style_violations") or 0)
    if 0 < style_violations <= 10:
        recommendations.nice_to_have.append(
            f"{style_violations} style violations remain low-risk polish items when review capacity allows."
        )

    return ManagerTeamInsights(actionable_recommendations=recommendations)


def _normalise_team_insights(
    raw: dict,
    scores: dict[str, float | int | None],
    metrics: dict,
) -> ManagerTeamInsights:
    fallback = _fallback_team_insights(scores, metrics)
    raw_buckets = raw.get("actionable_recommendations")
    if not isinstance(raw_buckets, dict):
        return fallback

    recommendations = _empty_actionable_recommendations()
    for bucket in RECOMMENDATION_BUCKET_KEYS:
        items = _normalise_recommendation_items(raw_buckets.get(bucket))
        setattr(recommendations, bucket, items if items else getattr(fallback.actionable_recommendations, bucket))

    if not any(getattr(recommendations, bucket) for bucket in RECOMMENDATION_BUCKET_KEYS):
        return fallback

    return ManagerTeamInsights(actionable_recommendations=recommendations)


def _manager_team_insight_payload(insights: ManagerTeamInsights) -> dict:
    return {
        "style_version": MANAGER_INSIGHT_STYLE_VERSION,
        "actionable_recommendations": _model_to_dict(insights.actionable_recommendations),
    }


def _merge_preserved_member_details(existing: object, new_insights: dict) -> dict:
    result = dict(new_insights)
    if isinstance(existing, dict) and isinstance(existing.get("member_detail_insights"), dict):
        result["member_detail_insights"] = existing["member_detail_insights"]
    return result


def _latest_manager_analysis_run(
    db: Session,
    manager_id: int,
    repo_id: int | None = None,
) -> AnalysisRun | None:
    query = (
        db.query(AnalysisRun)
        .filter(
            AnalysisRun.user_id == manager_id,
            AnalysisRun.status == "completed",
        )
    )
    if repo_id is not None:
        query = query.filter(AnalysisRun.repository_id == repo_id)

    return (
        query
        .order_by(AnalysisRun.completed_at.desc(), AnalysisRun.triggered_at.desc())
        .first()
    )


def _insights_from_payload(payload: dict) -> ManagerTeamInsights | None:
    buckets = payload.get("actionable_recommendations")
    if not isinstance(buckets, dict):
        return None

    recommendations = _empty_actionable_recommendations()
    for bucket in RECOMMENDATION_BUCKET_KEYS:
        setattr(recommendations, bucket, _normalise_recommendation_items(buckets.get(bucket)))

    return ManagerTeamInsights(actionable_recommendations=recommendations)


def _cached_team_insights(payload: dict | None) -> ManagerTeamInsights | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("style_version") != MANAGER_INSIGHT_STYLE_VERSION:
        return None
    return _insights_from_payload(payload)


def _trend_point_from_rows(
    period: str,
    label: str,
    rows: list[ScoreRow],
) -> ManagerTrendPoint:
    scores = _build_team_score_payload(rows)
    return ManagerTrendPoint(
        period=period,
        label=label,
        skill_score=scores.get("skill_score"),
        skill_score_level=classify_skill_score(scores.get("skill_score")),
        sonar_health_score=scores.get("sonar_health_score"),
        bugs=scores.get("bugs"),
        code_smells=scores.get("code_smells"),
        coverage=scores.get("coverage"),
        duplication_percentage=scores.get("duplication_percentage"),
        cognitive_complexity=scores.get("cognitive_complexity"),
        quality_gate_pass_rate=scores.get("quality_gate_pass_rate"),
    )


def _build_trend_points(rows: list[ScoreRow], range_key: str) -> list[ManagerTrendPoint]:
    range_key = _normalise_trend_range(range_key)
    filtered_rows = _filter_rows_by_trend_range(rows, range_key)
    grouped: dict[str, tuple[str, list[ScoreRow]]] = {}

    for row in filtered_rows:
        _, run, _, _ = row
        period, label = _trend_group_key(_run_time(run), range_key)
        if period not in grouped:
            grouped[period] = (label, [])
        grouped[period][1].append(row)

    return [
        _trend_point_from_rows(period, grouped[period][0], grouped[period][1])
        for period in sorted(grouped)
    ]


def _calculate_growth_rate(rows: list[ScoreRow]) -> float | None:
    points = _build_trend_points(rows, "all")
    if len(points) < 2:
        return None
    if points[-1].skill_score is None or points[-2].skill_score is None:
        return None
    return _round_score(points[-1].skill_score - points[-2].skill_score)


def _member_sonar_delta(rows: list[ScoreRow]) -> float | None:
    points = _build_trend_points(rows, "all")
    if len(points) < 2:
        return None
    if points[-1].skill_score is None or points[-2].skill_score is None:
        return None
    return _round_score(points[-1].skill_score - points[-2].skill_score)


def _member_from_rows(rows: list[ScoreRow]) -> ManagerTeamMember:
    user = rows[0][3]
    repo_ids = {row[1].repository_id for row in rows}
    scores = _build_team_score_payload(rows)
    latest_summary = _contributor_metric_payload_from_summary(rows[-1][0])

    return ManagerTeamMember(
        id=user.id,
        full_name=user.full_name,
        username=user.username,
        email=user.work_email,
        avatar_url=user.avatar_url,
        specialization=user.specialization.value if user.specialization else None,
        skill_score=scores.get("skill_score"),
        skill_score_level=classify_skill_score(scores.get("skill_score")),
        sonar_health_score=scores.get("sonar_health_score"),
        quality_gate=latest_summary.get("quality_gate"),
        bugs=scores.get("bugs"),
        code_smells=scores.get("code_smells"),
        coverage=scores.get("coverage"),
        duplication_percentage=scores.get("duplication_percentage"),
        cognitive_complexity=scores.get("cognitive_complexity"),
        repository_count=len(repo_ids),
        analysis_count=len(rows),
        sonar_delta=_member_sonar_delta(rows),
    )


def _normalise_member_detail_insights(raw: dict) -> tuple[list[str], list[str]]:
    strengths = _normalise_recommendation_items(raw.get("key_strengths"))
    improvements = _normalise_recommendation_items(raw.get("areas_for_improvement"))
    return strengths, improvements


def _member_detail_cache_root(user: User) -> dict:
    payload = user.global_team_insights
    if not isinstance(payload, dict):
        return {}
    member_details = payload.get("member_detail_insights")
    if not isinstance(member_details, dict):
        return {}
    return member_details


def _cached_member_detail_insights(
    user: User,
    member_id: int,
    run_ids: list[int],
) -> tuple[list[str], list[str]] | None:
    cached = _member_detail_cache_root(user).get(str(member_id))
    if not isinstance(cached, dict):
        return None
    if cached.get("style_version") != MEMBER_DETAIL_STYLE_VERSION:
        return None
    cached_run_ids = cached.get("run_ids")
    if not isinstance(cached_run_ids, list) or sorted(cached_run_ids) != sorted(run_ids):
        return None
    strengths = _normalise_recommendation_items(cached.get("key_strengths"))
    improvements = _normalise_recommendation_items(cached.get("areas_for_improvement"))
    return strengths, improvements


def _store_member_detail_insights(
    db: Session,
    user: User,
    member_id: int,
    run_ids: list[int],
    strengths: list[str],
    improvements: list[str],
) -> None:
    existing = user.global_team_insights if isinstance(user.global_team_insights, dict) else {}
    member_details = dict(existing.get("member_detail_insights") or {})
    member_details[str(member_id)] = {
        "style_version": MEMBER_DETAIL_STYLE_VERSION,
        "run_ids": sorted(run_ids),
        "key_strengths": strengths,
        "areas_for_improvement": improvements,
    }
    merged = dict(existing)
    merged["member_detail_insights"] = member_details
    user.global_team_insights = merged
    flag_modified(user, "global_team_insights")
    db.add(user)


async def _generate_and_store_member_detail_insights_from_rows(
    db: Session,
    current_user: User,
    member_rows: list[ScoreRow],
) -> tuple[list[str], list[str]]:
    if not member_rows:
        return [], []

    member = _member_from_rows(member_rows)
    timeline = _build_trend_points(member_rows, DEFAULT_TREND_RANGE)
    run_ids = _analysis_run_ids(member_rows)
    scores = _build_team_score_payload(member_rows)
    aggregate_metrics = _build_team_aggregate_metrics(db, run_ids)

    analysis_payload = {
        "developer": {
            "name": member.full_name,
            "specialization": member.specialization,
            "analysis_count": member.analysis_count,
            "repository_count": member.repository_count,
            "sonar_delta": member.sonar_delta,
        },
        "scores": scores,
        "aggregate_metrics": aggregate_metrics,
        "timeline": [_model_to_dict(point) for point in timeline],
        "manager_member_detail_prompt": MANAGER_MEMBER_DETAIL_PROMPT,
    }

    try:
        raw_insights = await generate_insights(
            role="manager_member",
            analysis_result=analysis_payload,
            security_report={},
            doc_id=STANDARDS_DOC_ID,
        )
    except Exception:
        raw_insights = {}

    raw_insights = raw_insights if isinstance(raw_insights, dict) else {}
    strengths, improvements = _normalise_member_detail_insights(raw_insights)
    _store_member_detail_insights(
        db,
        current_user,
        member.id,
        run_ids,
        strengths,
        improvements,
    )
    return strengths, improvements


def _number_or_none(value: object) -> float | int | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return int(numeric) if numeric.is_integer() else round(numeric, 2)


def _metric_value(summary: SonarAnalysisSummary | None, key: str) -> float | int | None:
    if summary is None:
        return None
    measures = summary.measures if isinstance(summary.measures, dict) else {}
    return _number_or_none(measures.get(key))


def _status_from_score(score: object) -> str:
    value = _number_or_none(score)
    if value is None:
        return "Unavailable"
    if float(value) >= 90:
        return "Excellent"
    if float(value) >= 75:
        return "Good"
    if float(value) >= 60:
        return "Fair"
    return "Needs Support"


def _repo_org(repo: Repository | None) -> str | None:
    if not repo or not repo.full_name or "/" not in repo.full_name:
        return None
    return repo.full_name.split("/", 1)[0]


def _summary_for_run(db: Session, run_id: int, user_id: int | None = None) -> SonarAnalysisSummary | None:
    query = db.query(SonarAnalysisSummary).filter(SonarAnalysisSummary.analysis_run_id == run_id)
    if user_id is not None:
        return query.filter(SonarAnalysisSummary.user_id == user_id).first()
    return query.first()


def _score_for_run(db: Session, run_id: int, user_id: int | None = None) -> SkillScore | None:
    query = db.query(SkillScore).filter(SkillScore.analysis_run_id == run_id)
    if user_id is not None:
        return query.filter(SkillScore.user_id == user_id).first()
    return query.first()


def _summary_sonar_health(summary: SonarAnalysisSummary | None, score: SkillScore | None = None) -> float | int | None:
    return _number_or_none(
        getattr(summary, "sonar_health_score", None)
        if summary is not None and summary.sonar_health_score is not None
        else getattr(score, "sonar_health_score", None)
    )


def _latest_team_security_run_for_repo(db: Session, manager_id: int, repo_id: int | None) -> AnalysisRun | None:
    if repo_id is None:
        return None
    return (
        db.query(AnalysisRun)
        .filter(
            AnalysisRun.user_id == manager_id,
            AnalysisRun.repository_id == repo_id,
            AnalysisRun.analysis_scope == "team_contributions",
            AnalysisRun.status == "completed",
        )
        .order_by(AnalysisRun.completed_at.desc(), AnalysisRun.triggered_at.desc())
        .first()
    )


def _team_security_score_for_runs(db: Session, run_ids: list[int]) -> float | None:
    """Mirror Team Security Health's repository score calculation."""
    if not run_ids:
        return None
    rows = (
        db.query(SkillScore.security_awareness_score)
        .join(User, SkillScore.user_id == User.id)
        .filter(
            SkillScore.analysis_run_id.in_(run_ids),
            User.role == UserRole.developer,
        )
        .all()
    )
    return _round_score(_avg([float(row[0] or 0.0) for row in rows]))


def _repository_security_score(db: Session, run: AnalysisRun | None, manager_id: int) -> float | None:
    """Return the same repo-level security score shown by Team Security Health."""
    team_security_run = _latest_team_security_run_for_repo(
        db,
        manager_id,
        getattr(run, "repository_id", None),
    )
    if team_security_run is None:
        return None
    return _team_security_score_for_runs(db, [team_security_run.id])


def _latest_repository_runs(
    db: Session,
    manager_id: int,
    repo_id: int | None = None,
) -> list[AnalysisRun]:
    query = (
        db.query(AnalysisRun)
        .filter(
            AnalysisRun.user_id == manager_id,
            AnalysisRun.status == "completed",
            AnalysisRun.analysis_scope == "repository",
        )
    )
    if repo_id is not None:
        query = query.filter(AnalysisRun.repository_id == repo_id)

    runs = query.order_by(AnalysisRun.completed_at.desc(), AnalysisRun.triggered_at.desc()).all()
    latest: dict[int, AnalysisRun] = {}
    for run in runs:
        if run.repository_id not in latest:
            latest[run.repository_id] = run
    return sorted(latest.values(), key=_run_time, reverse=True)


def _latest_repository_run(db: Session, manager_id: int, repo_id: int | None = None) -> AnalysisRun | None:
    runs = _latest_repository_runs(db, manager_id, repo_id)
    return runs[0] if runs else None


def _overview_repositories(db: Session, manager_id: int) -> list[ManagerDashboardRepo]:
    repos: list[ManagerDashboardRepo] = []
    for run in _latest_repository_runs(db, manager_id):
        contributor_rows = _latest_contributor_summaries(db, manager_id, run.repository_id)
        repos.append(
            ManagerDashboardRepo(
                id=run.repository.id,
                name=run.repository.name,
                full_name=run.repository.full_name,
                is_private=bool(run.repository.is_private),
                last_analyzed_at=run.completed_at,
                analysis_count=1,
                member_count=len({user.id for _, _, _, user in contributor_rows}),
            )
        )
    return repos


def _repository_summary(
    db: Session,
    run: AnalysisRun | None,
    manager_id: int,
) -> ManagerDashboardRepositorySummary:
    if run is None:
        return ManagerDashboardRepositorySummary()
    score = _score_for_run(db, run.id, manager_id)
    overall = _number_or_none(getattr(score, "overall_score", None))
    return ManagerDashboardRepositorySummary(
        analysis_run_id=run.id,
        repository_id=run.repository_id,
        repository_name=run.repository.full_name or run.repository.name,
        organization=_repo_org(run.repository),
        branch=run.branch,
        last_analysis=run.completed_at or run.triggered_at,
        analyzed_on=run.completed_at,
        overall_repository_score=overall,
        repository_status=_status_from_score(overall),
    )


def _repository_metric_cards(
    db: Session,
    run: AnalysisRun | None,
    manager_id: int,
) -> list[ManagerDashboardMetricCard]:
    score = _score_for_run(db, run.id, manager_id) if run else None
    summary = _summary_for_run(db, run.id, manager_id) if run else None
    overall = _number_or_none(getattr(score, "overall_score", None))
    health = _summary_sonar_health(summary, score)
    security = _repository_security_score(db, run, manager_id)
    coverage = _metric_value(summary, "coverage")
    bugs = _metric_value(summary, "bugs")
    smells = _metric_value(summary, "code_smells")
    duplication = _metric_value(summary, "duplicated_lines_density")
    complexity = _metric_value(summary, "cognitive_complexity")
    if complexity is None:
        complexity = _metric_value(summary, "complexity")

    return [
        ManagerDashboardMetricCard(key="overall_score", label="Overall Score", value=overall, status=_status_from_score(overall)),
        ManagerDashboardMetricCard(key="sonar_health_score", label="Sonar Health Score", value=health, status=_status_from_score(health)),
        ManagerDashboardMetricCard(key="security_score", label="Security Score", value=security, status=_status_from_score(security)),
        ManagerDashboardMetricCard(key="quality_gate", label="Quality Gate", value=getattr(summary, "quality_gate", None) if summary else None),
        ManagerDashboardMetricCard(key="coverage", label="Coverage", value=coverage, unit="%"),
        ManagerDashboardMetricCard(key="bugs", label="Bugs", value=bugs),
        ManagerDashboardMetricCard(key="code_smells", label="Code Smells", value=smells),
        ManagerDashboardMetricCard(key="duplication", label="Duplication", value=duplication, unit="%"),
        ManagerDashboardMetricCard(key="complexity", label="Complexity", value=complexity),
    ]


def _latest_contributor_score_rows(rows: list[ScoreRow]) -> list[ScoreRow]:
    latest: dict[int, ScoreRow] = {}
    for row in rows:
        _, run, _, user = row
        if user.id not in latest or _run_time(run) >= _run_time(latest[user.id][1]):
            latest[user.id] = row
    return list(latest.values())


def _sum_optional(values: Iterable[object]) -> float | int | None:
    numbers = [float(value) for value in values if _number_or_none(value) is not None]
    if not numbers:
        return None
    total = sum(numbers)
    return int(total) if float(total).is_integer() else _round_score(total)


def _weighted_average(pairs: Iterable[tuple[object, object]]) -> float | int | None:
    numerator = 0.0
    denominator = 0.0
    for value, weight in pairs:
        numeric_value = _number_or_none(value)
        numeric_weight = _number_or_none(weight)
        if numeric_value is None:
            continue
        weight_value = float(numeric_weight) if numeric_weight is not None and float(numeric_weight) > 0 else 1.0
        numerator += float(numeric_value) * weight_value
        denominator += weight_value
    if denominator <= 0:
        return None
    result = numerator / denominator
    return int(result) if float(result).is_integer() else _round_score(result)


def _contributor_metric_payload(row: ScoreRow) -> dict:
    return _contributor_metric_payload_from_summary(row[0])


def _contributor_rows(db: Session, score_rows: list[ScoreRow]) -> list[ManagerDashboardContributorRow]:
    contributors: list[ManagerDashboardContributorRow] = []
    for row in _latest_contributor_score_rows(score_rows):
        _, _, _, user = row
        metrics = _contributor_metric_payload(row)
        contributors.append(
            ManagerDashboardContributorRow(
                id=user.id,
                developer=user.full_name,
                username=user.username,
                role=user.specialization.value if user.specialization else "Developer",
                skill_score=metrics["skill_score"],
                health_score=metrics["health_score"],
                security_score=metrics["security_score"],
                coverage=metrics["coverage"],
                bugs=metrics["bugs"],
                code_smells=metrics["code_smells"],
                complexity=metrics["complexity"],
                status=_status_from_score(metrics["skill_score"]),
            )
        )
    return sorted(contributors, key=lambda item: item.skill_score if item.skill_score is not None else -1, reverse=True)


def _highlight_reason(name: str | None, row: ManagerDashboardContributorRow | None, support: bool = False) -> str | None:
    if row is None:
        return None
    if support:
        return (
            f"{name or row.developer} needs support because the latest skill score is "
            f"{row.skill_score if row.skill_score is not None else 'unavailable'} with health "
            f"{row.health_score if row.health_score is not None else 'unavailable'} and coverage "
            f"{row.coverage if row.coverage is not None else 'unavailable'}."
        )
    return (
        f"{name or row.developer} leads the latest contributor snapshot with skill score "
        f"{row.skill_score if row.skill_score is not None else 'unavailable'} and security score "
        f"{row.security_score if row.security_score is not None else 'unavailable'}."
    )


def _team_performance(contributors: list[ManagerDashboardContributorRow]) -> ManagerDashboardTeamPerformance:
    scored = [row for row in contributors if row.skill_score is not None]
    best = scored[0] if scored else None
    support = scored[-1] if scored else None
    best_highlight = (
        ManagerDashboardContributorHighlight(
            id=best.id,
            full_name=best.developer,
            username=best.username,
            score=best.skill_score,
            reasoning=_highlight_reason(best.developer, best),
        )
        if best else None
    )
    support_highlight = (
        ManagerDashboardContributorHighlight(
            id=support.id,
            full_name=support.developer,
            username=support.username,
            score=support.skill_score,
            reasoning=_highlight_reason(support.developer, support, support=True),
        )
        if support else None
    )
    return ManagerDashboardTeamPerformance(
        average_team_score=_avg_optional(row.skill_score for row in contributors),
        average_team_security_score=_avg_optional(row.security_score for row in contributors),
        average_coverage=_avg_optional(row.coverage for row in contributors),
        average_code_smells=_sum_optional(row.code_smells for row in contributors),
        best_contributor=best_highlight,
        needs_support_contributor=support_highlight,
        total_contributors=len(contributors),
    )


def _severity_rank(value: str | None) -> int:
    severity = normalize_severity(value)
    return {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(severity, 0)


def _issue_count_severity(count: int) -> str:
    if count >= 5:
        return "High"
    if count >= 2:
        return "Medium"
    return "Low"


def _file_name_from_path(path: str | None) -> str:
    value = (path or "Unknown file").replace("\\", "/")
    return value.rsplit("/", 1)[-1] or "Unknown file"


def _build_issue_file_risks(
    issues: list[SonarIssue],
    issue_label: str,
) -> list[ManagerDashboardRiskItem]:
    grouped: dict[str, list[SonarIssue]] = defaultdict(list)
    for issue in issues:
        grouped[issue.file_path or "Unknown file"].append(issue)

    items: list[ManagerDashboardRiskItem] = []
    for path, file_issues in grouped.items():
        count = len(file_issues)
        items.append(
            ManagerDashboardRiskItem(
                title=_file_name_from_path(path),
                detail=f"{count} {issue_label}(s) found in this file.",
                file_path=path,
                metric=count,
                severity=_issue_count_severity(count),
                count=count,
            )
        )

    return sorted(items, key=lambda item: item.count or 0, reverse=True)[:5]


def _risk_groups(db: Session, run: AnalysisRun | None) -> ManagerDashboardRiskGroups:
    if run is None:
        return ManagerDashboardRiskGroups()

    issue_rows = (
        db.query(SonarIssue)
        .filter(SonarIssue.analysis_run_id == run.id)
        .all()
    )

    code_smell_issues = [
        issue for issue in issue_rows
        if str(issue.type or "").upper() == "CODE_SMELL"
    ]
    bug_issues = [
        issue for issue in issue_rows
        if str(issue.type or "").upper() == "BUG"
    ]

    bug_file_risks = _build_issue_file_risks(bug_issues, "bug")

    return ManagerDashboardRiskGroups(
        high_code_smells=_build_issue_file_risks(code_smell_issues, "code smell"),
        high_bug_files=bug_file_risks,
        files_for_bugs=bug_file_risks,
    )


def _normalise_overview_trend_granularity(value: str | None) -> str:
    value = (value or "monthly").strip().lower()
    return value if value in {"daily", "monthly"} else "monthly"


def _overview_trend_bucket(run_time: datetime, granularity: str) -> tuple[str, str]:
    if granularity == "daily":
        return run_time.strftime("%Y-%m-%d"), run_time.strftime("%b %d")
    return run_time.strftime("%Y-%m"), run_time.strftime("%b %Y")


def _repository_trend_data(
    db: Session,
    manager_id: int,
    repo_id: int | None,
    granularity: str,
) -> dict[str, dict[str, list[float]]]:
    granularity = _normalise_overview_trend_granularity(granularity)
    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    repository_query = (
        db.query(AnalysisRun)
        .filter(
            AnalysisRun.user_id == manager_id,
            AnalysisRun.status == "completed",
            AnalysisRun.analysis_scope == "repository",
        )
    )
    if repo_id is not None:
        repository_query = repository_query.filter(AnalysisRun.repository_id == repo_id)
    repository_runs = repository_query.order_by(AnalysisRun.completed_at.asc(), AnalysisRun.triggered_at.asc()).all()

    for run in repository_runs:
        period, label = _overview_trend_bucket(_run_time(run), granularity)
        summary = _summary_for_run(db, run.id, manager_id)
        score = _score_for_run(db, run.id, manager_id)
        health = _summary_sonar_health(summary, score)
        grouped[period]["_label"] = [label]  # type: ignore[assignment]
        if health is not None:
            grouped[period]["health_score"].append(float(health))

    security_query = (
        db.query(AnalysisRun)
        .filter(
            AnalysisRun.user_id == manager_id,
            AnalysisRun.status == "completed",
            AnalysisRun.analysis_scope == "team_contributions",
        )
    )
    if repo_id is not None:
        security_query = security_query.filter(AnalysisRun.repository_id == repo_id)
    security_runs = security_query.order_by(AnalysisRun.completed_at.asc(), AnalysisRun.triggered_at.asc()).all()

    for run in security_runs:
        period, label = _overview_trend_bucket(_run_time(run), granularity)
        security = _team_security_score_for_runs(db, [run.id])
        grouped[period]["_label"] = grouped[period].get("_label") or [label]  # type: ignore[assignment]
        if security is not None:
            grouped[period]["security_score"].append(float(security))
    return grouped


def _build_overview_trends(
    db: Session,
    manager_id: int,
    repo_id: int | None,
    granularity: str = "monthly",
) -> list[ManagerDashboardOverviewTrendPoint]:
    granularity = _normalise_overview_trend_granularity(granularity)
    repository_data = _repository_trend_data(db, manager_id, repo_id, granularity)
    points: list[ManagerDashboardOverviewTrendPoint] = []
    for period in sorted(repository_data):
        metrics = repository_data.get(period, {})
        label_values = metrics.get("_label") or [period]
        points.append(
            ManagerDashboardOverviewTrendPoint(
                period=period,
                label=str(label_values[0]),
                health_score=_avg_optional(metrics.get("health_score", [])),
                security_score=_avg_optional(metrics.get("security_score", [])),
            )
        )
    limit = 30 if granularity == "daily" else 12
    return points[-limit:]


def _list_from_llm(raw: dict, key: str) -> list[str]:
    value = raw.get(key)
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return _normalise_recommendation_items(value)


def _normalise_overview_recommendations(raw: object) -> ManagerDashboardRecommendations:
    raw = raw if isinstance(raw, dict) else {}
    bucket_values = {key: _list_from_llm(raw, key) for key in OVERVIEW_RECOMMENDATION_KEYS}
    recommendations = ManagerDashboardRecommendations(
        fix_first=bucket_values["fix_first"],
        prioritize_next=bucket_values["prioritize_next"],
        plan_when_possible=bucket_values["plan_when_possible"],
        strengthen_further=bucket_values["strengthen_further"],
        architectural_concerns=bucket_values["architectural_concerns"],
        delivery_risks=bucket_values["delivery_risks"],
        quality_concerns=bucket_values["quality_concerns"],
        team_strengths=bucket_values["team_strengths"],
        recommended_priorities=bucket_values["recommended_priorities"],
    )
    recommendations.actionable_recommendations = [
        *recommendations.fix_first,
        *recommendations.prioritize_next,
        *recommendations.plan_when_possible,
    ]
    recommendations.prioritized_team_next_moves = recommendations.recommended_priorities[:3]
    recommendations.team_improvement_guidance = [
        *recommendations.strengthen_further,
        *recommendations.team_strengths,
    ][:3]
    return recommendations


def _sonar_summary_payload(summary: SonarAnalysisSummary | None, score: SkillScore | None, security_score: float | None) -> dict:
    if summary is None and score is None:
        return {}
    return {
        "repository_score": _number_or_none(getattr(score, "overall_score", None)),
        "skill_score": _number_or_none(getattr(score, "overall_score", None)),
        "sonarqube_health_score": _summary_sonar_health(summary, score),
        "security_score": _number_or_none(security_score),
        "quality_gate": getattr(summary, "quality_gate", None) if summary else None,
        "coverage": _metric_value(summary, "coverage"),
        "bugs": _metric_value(summary, "bugs"),
        "code_smells": _metric_value(summary, "code_smells"),
        "duplication_percentage": _metric_value(summary, "duplicated_lines_density"),
        "complexity": _metric_value(summary, "complexity"),
        "cognitive_complexity": _metric_value(summary, "cognitive_complexity"),
    }


def _file_measure_risk_score(row: SonarFileMeasure) -> float:
    coverage = _number_or_none(row.coverage)
    duplication = _number_or_none(row.duplicated_lines_density)
    complexity = _number_or_none(row.complexity)
    cognitive = _number_or_none(row.cognitive_complexity)
    risk = float(cognitive or 0) + float(complexity or 0) + float(duplication or 0)
    if coverage is not None:
        risk += max(0.0, 100.0 - float(coverage)) / 2
    return risk


def _top_risky_files_payload(db: Session, run: AnalysisRun) -> list[dict]:
    rows = (
        db.query(SonarFileMeasure)
        .filter(SonarFileMeasure.analysis_run_id == run.id)
        .all()
    )
    ranked = sorted(rows, key=_file_measure_risk_score, reverse=True)
    return [
        {
            "file_path": row.file_path,
            "coverage": _number_or_none(row.coverage),
            "duplicated_lines": _number_or_none(row.duplicated_lines),
            "duplication_percentage": _number_or_none(row.duplicated_lines_density),
            "ncloc": _number_or_none(row.ncloc),
            "complexity": _number_or_none(row.complexity),
            "cognitive_complexity": _number_or_none(row.cognitive_complexity),
            "functions": _number_or_none(row.functions),
            "classes": _number_or_none(row.classes),
        }
        for row in ranked[:10]
        if _file_measure_risk_score(row) > 0
    ]


def _top_sonar_issues_payload(db: Session, run: AnalysisRun) -> list[dict]:
    rows = (
        db.query(SonarIssue)
        .filter(SonarIssue.analysis_run_id == run.id)
        .all()
    )
    ranked = sorted(rows, key=lambda issue: (_severity_rank(issue.severity), str(issue.type or "")), reverse=True)
    return [
        {
            "issue_key": issue.issue_key,
            "file_path": issue.file_path,
            "line": issue.line,
            "type": issue.type,
            "severity": issue.severity,
            "rule": issue.rule,
            "message": issue.message,
            "status": issue.status,
        }
        for issue in ranked[:15]
    ]


def _top_security_findings_payload(db: Session, run: AnalysisRun) -> list[dict]:
    rows = (
        db.query(SecurityFinding)
        .filter(SecurityFinding.analysis_run_id == run.id)
        .all()
    )
    ranked = sorted(rows, key=lambda finding: _severity_rank(finding.severity), reverse=True)
    return [
        {
            "tool": finding.tool,
            "rule": finding.rule,
            "cwe": finding.cwe,
            "file_path": finding.file_path,
            "severity": normalize_severity(finding.severity),
            "description": finding.description,
            "line_number": finding.line_number,
            "owasp_category": finding.owasp_category,
        }
        for finding in ranked[:15]
    ]


def _contributor_recommendation_payload(rows: list[ScoreRow], repository_id: int) -> list[dict]:
    contributors: list[dict] = []
    repository_rows = [row for row in rows if row[2].id == repository_id]
    for row in _latest_contributor_score_rows(repository_rows):
        summary, run, repository, user = row
        contributors.append(
            {
                "repository_id": repository.id,
                "analysis_run_id": run.id,
                "developer_id": user.id,
                "developer": user.full_name,
                "username": user.username,
                "contributor_login": summary.contributor_login,
                "files_count": summary.files_count,
                "touched_files": summary.touched_files if isinstance(summary.touched_files, list) else [],
                **_contributor_metric_payload_from_summary(summary),
            }
        )
    return contributors


def _repository_manager_recommendation_payload(
    db: Session,
    run: AnalysisRun | None,
    manager_id: int,
    contributor_rows: list[ScoreRow],
    risks: ManagerDashboardRiskGroups,
) -> dict:
    if run is None:
        return {}
    score = _score_for_run(db, run.id, manager_id)
    summary = _summary_for_run(db, run.id, manager_id)
    security_score = _repository_security_score(db, run, manager_id)
    return {
        "repository": {
            "id": run.repository.id,
            "name": run.repository.name,
            "full_name": run.repository.full_name,
            "branch": run.branch,
            "latest_analysis_run_id": run.id,
        },
        "scores": _sonar_summary_payload(summary, score, security_score),
        "top_risky_files": _top_risky_files_payload(db, run),
        "top_sonar_issues": _top_sonar_issues_payload(db, run),
        "top_security_findings": _top_security_findings_payload(db, run),
        "contributors": _contributor_recommendation_payload(contributor_rows, run.repository_id),
        "risk_groups": _model_to_dict(risks),
    }


async def _overview_recommendations(
    db: Session,
    repository_run: AnalysisRun | None,
    manager_id: int,
    contributor_rows: list[ScoreRow],
    risks: ManagerDashboardRiskGroups,
) -> ManagerDashboardRecommendations:
    payload = _repository_manager_recommendation_payload(
        db=db,
        run=repository_run,
        manager_id=manager_id,
        contributor_rows=contributor_rows,
        risks=risks,
    )
    raw = await run_in_threadpool(generate_repository_manager_recommendations, payload)
    return _normalise_overview_recommendations(raw)


@router.get("/overview", response_model=ManagerDashboardOverview)
async def get_manager_dashboard_overview(
    repo_id: int | None = Query(default=None),
    trend_granularity: str = Query(default="monthly"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["manager"])),
):
    repositories = _overview_repositories(db, current_user.id)
    repository_run = _latest_repository_run(db, current_user.id, repo_id)
    if repo_id is not None and repository_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository dashboard data not found.")

    effective_repo_id = repository_run.repository_id if repository_run else repo_id
    team_rows = _query_manager_score_rows(db, current_user.id, effective_repo_id)
    contributors = _contributor_rows(db, team_rows)
    team_performance = _team_performance(contributors)
    repository_metrics = _repository_metric_cards(db, repository_run, current_user.id)
    risks = _risk_groups(db, repository_run)
    recommendations = await _overview_recommendations(
        db=db,
        repository_run=repository_run,
        manager_id=current_user.id,
        contributor_rows=team_rows,
        risks=risks,
    )

    if team_performance.best_contributor and recommendations.best_contributor_reasoning:
        team_performance.best_contributor.reasoning = recommendations.best_contributor_reasoning
    if team_performance.needs_support_contributor and recommendations.needs_support_reasoning:
        team_performance.needs_support_contributor.reasoning = recommendations.needs_support_reasoning

    return ManagerDashboardOverview(
        repositories=repositories,
        repository_summary=_repository_summary(db, repository_run, current_user.id),
        repository_metrics=repository_metrics,
        team_performance=team_performance,
        contributors=contributors,
        trends=_build_overview_trends(db, current_user.id, effective_repo_id, trend_granularity),
        risks=risks,
        recommendations=recommendations,
    )


@router.get("/repos", response_model=list[ManagerDashboardRepo])
def get_manager_dashboard_repos(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["manager"])),
):
    rows = (
        db.query(
            Repository.id,
            Repository.name,
            Repository.full_name,
            Repository.is_private,
            func.max(AnalysisRun.completed_at).label("last_analyzed_at"),
            func.count(func.distinct(AnalysisRun.id)).label("analysis_count"),
            func.count(func.distinct(ContributorAnalysisSummary.user_id)).label("member_count"),
        )
        .join(AnalysisRun, AnalysisRun.repository_id == Repository.id)
        .join(ContributorAnalysisSummary, ContributorAnalysisSummary.analysis_run_id == AnalysisRun.id)
        .join(User, ContributorAnalysisSummary.user_id == User.id)
        .filter(
            AnalysisRun.user_id == current_user.id,
            AnalysisRun.status == "completed",
            AnalysisRun.analysis_scope == "team_contributions",
            User.role == UserRole.developer,
        )
        .group_by(Repository.id, Repository.name, Repository.full_name, Repository.is_private)
        .order_by(func.max(AnalysisRun.completed_at).desc())
        .all()
    )

    return [
        ManagerDashboardRepo(
            id=row.id,
            name=row.name,
            full_name=row.full_name,
            is_private=bool(row.is_private),
            last_analyzed_at=row.last_analyzed_at,
            analysis_count=int(row.analysis_count or 0),
            member_count=int(row.member_count or 0),
        )
        for row in rows
    ]


@router.get("/kpis", response_model=ManagerKpis)
def get_manager_dashboard_kpis(
    repo_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["manager"])),
):
    rows = _query_manager_score_rows(db, current_user.id, repo_id)
    developer_averages = _average_sonar_by_developer(rows)
    users_by_id = {user.id: user for _, _, _, user in rows}

    team_skill_average = _team_average_from_developer_averages(developer_averages, "skill_score")
    team_sonar_average = _team_average_from_developer_averages(developer_averages, "sonar_health_score")
    top_performer: ManagerTopPerformer | None = None
    if developer_averages:
        ready = [
            (user_id, scores)
            for user_id, scores in developer_averages.items()
            if scores.get("skill_score") is not None
        ]
        if ready:
            top_user_id, top_scores = max(
                ready,
                key=lambda item: item[1].get("skill_score") or -1,
            )
            top_user = users_by_id[top_user_id]
            top_performer = ManagerTopPerformer(
                id=top_user.id,
                full_name=top_user.full_name,
                username=top_user.username,
                skill_score=top_scores.get("skill_score"),
                skill_score_level=classify_skill_score(top_scores.get("skill_score")),
                sonar_health_score=top_scores.get("sonar_health_score"),
            )

    return ManagerKpis(
        team_skill_score=team_skill_average,
        team_skill_score_level=classify_skill_score(team_skill_average),
        team_sonar_health_score=team_sonar_average,
        team_size=len(developer_averages),
        top_performer=top_performer,
        growth_rate=_calculate_growth_rate(rows),
    )


@router.get("/trends", response_model=list[ManagerTrendPoint])
def get_manager_dashboard_trends(
    repo_id: int | None = Query(default=None),
    range: str = Query(default=DEFAULT_TREND_RANGE),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["manager"])),
):
    rows = _query_manager_score_rows(db, current_user.id, repo_id)
    return _build_trend_points(rows, range)


@router.get("/skills", response_model=ManagerSkillDistribution)
def get_manager_dashboard_skills(
    repo_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["manager"])),
):
    rows = _query_manager_score_rows(db, current_user.id, repo_id)
    scores = _build_team_score_payload(rows)

    return ManagerSkillDistribution(
        skill_score=scores.get("skill_score"),
        skill_score_level=classify_skill_score(scores.get("skill_score")),
        sonar_health_score=scores.get("sonar_health_score"),
        bugs=scores.get("bugs"),
        code_smells=scores.get("code_smells"),
        coverage=scores.get("coverage"),
        duplication_percentage=scores.get("duplication_percentage"),
        cognitive_complexity=scores.get("cognitive_complexity"),
        quality_gate_pass_rate=scores.get("quality_gate_pass_rate"),
    )


@router.get("/insights", response_model=ManagerTeamInsights)
async def get_manager_dashboard_insights(
    repo_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["manager"])),
):
    latest_repo_run: AnalysisRun | None = None
    if repo_id is None:
        cached = _cached_team_insights(current_user.global_team_insights)
    else:
        latest_repo_run = _latest_manager_analysis_run(db, current_user.id, repo_id)
        cached = _cached_team_insights(
            latest_repo_run.ai_insights if latest_repo_run else None
        )

    if cached:
        return cached

    rows = _query_manager_score_rows(db, current_user.id, repo_id)
    if not rows:
        return ManagerTeamInsights(actionable_recommendations=_empty_actionable_recommendations())

    scores = _build_team_score_payload(rows)
    run_ids = _analysis_run_ids(rows)
    aggregate_metrics = _build_team_aggregate_metrics(db, run_ids)
    analysis_payload = {
        "scores": scores,
        "aggregate_metrics": {
            **aggregate_metrics,
            "team_size": len({user.id for _, _, _, user in rows}),
            "repository_count": len({run.repository_id for _, run, _, _ in rows}),
        },
        "manager_dashboard_prompt": MANAGER_DASHBOARD_PROMPT,
    }

    try:
        raw_insights = await generate_insights(
            role="manager",
            analysis_result=analysis_payload,
            security_report={},
            doc_id=STANDARDS_DOC_ID,
        )
    except Exception:
        raw_insights = {}

    raw_insights = raw_insights if isinstance(raw_insights, dict) else {}
    insights = _normalise_team_insights(
        raw_insights,
        scores,
        aggregate_metrics,
    )
    pure_insights = _manager_team_insight_payload(insights)

    if "actionable_recommendations" in raw_insights:
        if repo_id is None:
            current_user.global_team_insights = _merge_preserved_member_details(
                current_user.global_team_insights,
                pure_insights,
            )
            flag_modified(current_user, "global_team_insights")
            db.add(current_user)
        elif latest_repo_run:
            latest_repo_run.ai_insights = pure_insights
        db.commit()

    return insights


@router.get("/members", response_model=list[ManagerTeamMember])
def get_manager_dashboard_members(
    repo_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["manager"])),
):
    rows = _query_manager_score_rows(db, current_user.id, repo_id)
    by_user: dict[int, list[ScoreRow]] = defaultdict(list)
    for row in rows:
        _, _, _, user = row
        by_user[user.id].append(row)

    members = [_member_from_rows(user_rows) for user_rows in by_user.values()]
    return sorted(members, key=lambda member: member.skill_score if member.skill_score is not None else -1, reverse=True)


@router.get("/members/{member_id}/details", response_model=ManagerMemberDetail)
def get_manager_dashboard_member_details(
    member_id: int,
    range: str = Query(default=DEFAULT_TREND_RANGE),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["manager"])),
):
    rows = _query_manager_score_rows(db, current_user.id)
    member_rows = [row for row in rows if row[3].id == member_id]
    if not member_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Developer not found in manager dashboard scope.",
        )

    member = _member_from_rows(member_rows)
    timeline = _build_trend_points(member_rows, range)
    run_ids = _analysis_run_ids(member_rows)
    cached_insights = _cached_member_detail_insights(current_user, member_id, run_ids)
    strengths, improvements = cached_insights if cached_insights is not None else ([], [])

    return ManagerMemberDetail(
        member=member,
        timeline=timeline,
        key_strengths=strengths,
        areas_for_improvement=improvements,
    )
