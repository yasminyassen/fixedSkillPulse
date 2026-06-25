from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
import uuid
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm.attributes import flag_modified
from app.db.database import SessionLocal
from app.db.models import (
    AnalysisRun,
    CodeMetrics,
    ContributorAnalysisSummary,
    Repository,
    RepositoryAnalysis,
    RepositoryContributor,
    SecurityFinding,
    SkillScore,
    SonarAnalysisSummary,
    SonarFileMeasure,
    SonarIssue,
    User,
    UserRole,
)
from app.services.security.pipeline import run_security_analysis
from app.services.github_client import (
    read_local_repo_files,
    refresh_github_access_token_for_user,
    fetch_authenticated_github_user,
    fetch_repository_commit_contributions,
)
from app.services.code_intelligence import analyze_python_files
from app.services.llm_client import LLMError, analyze_skill_gaps_with_llm
from app.services.metrics import build_unified_schema
from app.services.learning_recommendations import build_learning_recommendations
from app.api.manager_dashboard import (
    _analysis_run_ids,
    _build_team_aggregate_metrics,
    _build_team_score_payload,
    _generate_and_store_member_detail_insights_from_rows,
    _manager_team_insight_payload,
    _normalise_team_insights,
    _query_manager_score_rows,
)
from ai_services.insights.ai_insights import generate_insights
from ai_services.rag.rag_seeder import STANDARDS_DOC_ID
from app.core.auth_utils import decrypt_github_token
from app.services.security_service import compute_security_score_breakdown, group_findings_by_severity_and_file
from app.services.sonarqube_service import run_sonar_analysis
from app.services.sonarqube_score_service import compute_skill_score_engine, compute_sonar_health_score


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _build_manager_dashboard_payload(rows: list, db: Session) -> dict:
    scores = _build_team_score_payload(rows)
    aggregate_metrics = _build_team_aggregate_metrics(db, _analysis_run_ids(rows))
    return {
        "scores": scores,
        "aggregate_metrics": {
            **aggregate_metrics,
            "team_size": len({user.id for _, _, _, user in rows}),
            "repository_count": len({run.repository_id for _, run, _, _ in rows}),
        },
    }


def _merge_preserved_member_details(existing: object, new_insights: dict) -> dict:
    result = dict(new_insights)
    if isinstance(existing, dict) and isinstance(existing.get("member_detail_insights"), dict):
        result["member_detail_insights"] = existing["member_detail_insights"]
    return result


def _model_to_dict(model: BaseModel) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _pure_manager_insights(
    raw_insights: object,
    scores: dict[str, float],
    metrics: dict,
) -> dict | None:
    if not isinstance(raw_insights, dict):
        return None
    if (
        "actionable_recommendations" not in raw_insights
    ):
        return None

    return _manager_team_insight_payload(
        _normalise_team_insights(raw_insights, scores, metrics)
    )


async def _generate_manager_dashboard_insights_from_rows(
    rows: list,
    db: Session,
    manager_user_id: int,
    scope: str,
) -> dict | None:
    if not rows:
        logger.info(
            "Skipped manager dashboard insight generation manager_user_id=%s scope=%s reason=no_rows",
            manager_user_id,
            scope,
        )
        return None

    analysis_payload = _build_manager_dashboard_payload(rows, db)
    raw_insights = await generate_insights(
        role="manager",
        analysis_result=analysis_payload,
        security_report={},
        doc_id=STANDARDS_DOC_ID,
    )
    pure_insights = _pure_manager_insights(
        raw_insights,
        analysis_payload["scores"],
        analysis_payload["aggregate_metrics"],
    )
    if pure_insights is None:
        logger.warning(
            "Manager dashboard LLM returned no cacheable team insights manager_user_id=%s scope=%s",
            manager_user_id,
            scope,
        )
    return pure_insights


class FindingModel(BaseModel):
    tool: str
    rule: str
    file_path: str
    severity: str
    description: str
    line_number: int
    cwe: str
    owasp_category: str


def _normalize_repo_path(path: str) -> str:
    return str(path or "").replace("\\", "/").lstrip("/").strip()


def _existing_python_contribution_files(repo_path: str, touched_files: list[str] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    repo_root = os.path.abspath(repo_path)

    for path in touched_files or []:
        normalized = _normalize_repo_path(path)
        if not normalized.endswith(".py"):
            continue
        absolute = os.path.abspath(os.path.join(repo_path, normalized))
        try:
            if os.path.commonpath([repo_root, absolute]) != repo_root:
                continue
        except ValueError:
            continue
        if not os.path.isfile(absolute):
            continue
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)

    return sorted(result)


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


def _float_or_none(value) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_project_measures(sonar_payload: dict | None) -> dict:
    if not isinstance(sonar_payload, dict):
        return {}
    measures = ((sonar_payload.get("measures") or {}).get("component") or {}).get("measures") or []
    return {
        item.get("metric"): item.get("value")
        for item in measures
        if isinstance(item, dict) and item.get("metric")
    }


def _extract_quality_gate(sonar_payload: dict | None) -> str | None:
    if not isinstance(sonar_payload, dict):
        return None
    status = ((sonar_payload.get("quality_gate") or {}).get("projectStatus") or {}).get("status")
    return str(status).upper() if status else None


def _extract_file_path_from_component_or_issue(value) -> str | None:
    if value is None:
        return None
    path = str(value).replace("\\", "/").strip()
    if ":" in path:
        path = path.rsplit(":", 1)[-1]
    path = path.lstrip("/")
    return path or None


def _measure_map(items: list[dict] | None) -> dict:
    return {
        item.get("metric"): item.get("value")
        for item in items or []
        if isinstance(item, dict) and item.get("metric")
    }


def _sonar_skill_gap_inputs(
    sonar_payload: dict | None,
    security_findings: list[dict],
) -> tuple[dict, list[dict], list[dict], list[dict]]:
    if not isinstance(sonar_payload, dict) or sonar_payload.get("error"):
        return {}, [], [], []

    project_measures = _extract_project_measures(sonar_payload)
    metric_keys = (
        "coverage",
        "bugs",
        "code_smells",
        "duplicated_lines_density",
        "complexity",
        "cognitive_complexity",
        "reliability_rating",
        "sqale_rating",
        "sqale_index",
    )
    sonar_metrics = {key: project_measures.get(key) for key in metric_keys}

    file_rows = []
    for component in (sonar_payload.get("file_measures") or {}).get("components") or []:
        if not isinstance(component, dict):
            continue
        measures = _measure_map(component.get("measures") or [])
        file_path = (
            _extract_file_path_from_component_or_issue(component.get("path"))
            or _extract_file_path_from_component_or_issue(component.get("name"))
            or _extract_file_path_from_component_or_issue(component.get("key"))
        )
        row = {
            "file_path": file_path,
            "coverage": _float_or_none(measures.get("coverage")),
            "complexity": _float_or_none(measures.get("complexity")),
            "cognitive_complexity": _float_or_none(measures.get("cognitive_complexity")),
            "duplication": _float_or_none(measures.get("duplicated_lines_density")),
            "uncovered_lines": _float_or_none(measures.get("uncovered_lines")),
        }
        if file_path and any(value is not None for key, value in row.items() if key != "file_path"):
            file_rows.append(row)

    def _risk(row: dict) -> float:
        coverage_risk = 100.0 - float(row["coverage"]) if row.get("coverage") is not None else 0.0
        complexity_risk = float(row.get("complexity") or 0.0)
        cognitive_risk = float(row.get("cognitive_complexity") or 0.0)
        duplication_risk = float(row.get("duplication") or 0.0) * 2
        return coverage_risk + complexity_risk + cognitive_risk + duplication_risk

    sonar_file_metrics = sorted(file_rows, key=_risk, reverse=True)[:20]

    sonar_issues = []
    for issue in (sonar_payload.get("issues") or {}).get("issues") or []:
        if not isinstance(issue, dict):
            continue
        issue_type = str(issue.get("type") or "").upper()
        if issue_type not in {"BUG", "CODE_SMELL"}:
            continue
        text_range = issue.get("textRange") or {}
        sonar_issues.append({
            "type": issue_type,
            "severity": issue.get("severity"),
            "rule": issue.get("rule"),
            "file_path": _extract_file_path_from_component_or_issue(issue.get("component")),
            "line": issue.get("line") or text_range.get("startLine"),
            "message": issue.get("message"),
        })

    security_rows = [
        {
            "severity": finding.get("severity"),
            "cwe": finding.get("cwe"),
            "rule": finding.get("rule"),
            "file_path": finding.get("file_path"),
            "description": finding.get("description"),
            "owasp_category": finding.get("owasp_category"),
        }
        for finding in security_findings
        if isinstance(finding, dict)
    ]
    return sonar_metrics, sonar_file_metrics, sonar_issues[:50], security_rows[:50]


def _persist_sonar_results(
    db: Session,
    run: AnalysisRun,
    user_id: int | None,
    sonar_result: dict,
    sonar_health_score: float | None,
) -> None:
    sonar_payload = sonar_result.get("sonar") if isinstance(sonar_result, dict) else None
    if not isinstance(sonar_payload, dict) or sonar_payload.get("error"):
        return

    db.query(SonarIssue).filter(SonarIssue.analysis_run_id == run.id).delete(synchronize_session=False)
    db.query(SonarFileMeasure).filter(SonarFileMeasure.analysis_run_id == run.id).delete(synchronize_session=False)
    db.query(SonarAnalysisSummary).filter(SonarAnalysisSummary.analysis_run_id == run.id).delete(synchronize_session=False)

    project_measures = _extract_project_measures(sonar_payload)
    db.add(SonarAnalysisSummary(
        analysis_run_id=run.id,
        user_id=user_id,
        project_key=sonar_result.get("project_key"),
        quality_gate=_extract_quality_gate(sonar_payload),
        sonar_health_score=sonar_health_score,
        measures=project_measures,
        coverage=sonar_payload.get("coverage"),
        scanner=sonar_payload.get("scanner"),
        ce_task=sonar_payload.get("ce_task"),
        raw_payload=sonar_payload,
    ))

    for component in (sonar_payload.get("file_measures") or {}).get("components") or []:
        if not isinstance(component, dict):
            continue
        file_path = (
            _extract_file_path_from_component_or_issue(component.get("path"))
            or _extract_file_path_from_component_or_issue(component.get("name"))
            or _extract_file_path_from_component_or_issue(component.get("key"))
        )
        if not file_path:
            continue
        measures = _measure_map(component.get("measures") or [])
        db.add(SonarFileMeasure(
            analysis_run_id=run.id,
            user_id=user_id,
            file_path=file_path,
            measures=measures,
            coverage=_float_or_none(measures.get("coverage")),
            duplicated_lines=_float_or_none(measures.get("duplicated_lines")),
            duplicated_lines_density=_float_or_none(measures.get("duplicated_lines_density")),
            ncloc=_float_or_none(measures.get("ncloc")),
            complexity=_float_or_none(measures.get("complexity")),
            cognitive_complexity=_float_or_none(measures.get("cognitive_complexity")),
            functions=_float_or_none(measures.get("functions")),
            classes=_float_or_none(measures.get("classes")),
            statements=_float_or_none(measures.get("statements")),
        ))

    for issue in (sonar_payload.get("issues") or {}).get("issues") or []:
        if not isinstance(issue, dict):
            continue
        if str(issue.get("status") or "").upper() == "CLOSED":
            continue
        text_range = issue.get("textRange") or {}
        db.add(SonarIssue(
            analysis_run_id=run.id,
            user_id=user_id,
            issue_key=issue.get("key"),
            file_path=_extract_file_path_from_component_or_issue(issue.get("component")),
            line=issue.get("line") or text_range.get("startLine"),
            type=issue.get("type"),
            severity=issue.get("severity"),
            rule=issue.get("rule"),
            message=issue.get("message"),
            status=issue.get("status"),
            raw_issue=issue,
        ))


def _persist_contributor_sonar_detail_rows(
    db: Session,
    run: AnalysisRun,
    user_id: int,
    sonar_result: dict,
) -> None:
    sonar_payload = sonar_result.get("sonar") if isinstance(sonar_result, dict) else None
    if not isinstance(sonar_payload, dict) or sonar_payload.get("error"):
        return

    db.query(SonarIssue).filter(
        SonarIssue.analysis_run_id == run.id,
        SonarIssue.user_id == user_id,
    ).delete(synchronize_session=False)
    db.query(SonarFileMeasure).filter(
        SonarFileMeasure.analysis_run_id == run.id,
        SonarFileMeasure.user_id == user_id,
    ).delete(synchronize_session=False)

    for component in (sonar_payload.get("file_measures") or {}).get("components") or []:
        if not isinstance(component, dict):
            continue
        file_path = (
            _extract_file_path_from_component_or_issue(component.get("path"))
            or _extract_file_path_from_component_or_issue(component.get("name"))
            or _extract_file_path_from_component_or_issue(component.get("key"))
        )
        if not file_path:
            continue
        measures = _measure_map(component.get("measures") or [])
        db.add(SonarFileMeasure(
            analysis_run_id=run.id,
            user_id=user_id,
            file_path=file_path,
            measures=measures,
            coverage=_float_or_none(measures.get("coverage")),
            duplicated_lines=_float_or_none(measures.get("duplicated_lines")),
            duplicated_lines_density=_float_or_none(measures.get("duplicated_lines_density")),
            ncloc=_float_or_none(measures.get("ncloc")),
            complexity=_float_or_none(measures.get("complexity")),
            cognitive_complexity=_float_or_none(measures.get("cognitive_complexity")),
            functions=_float_or_none(measures.get("functions")),
            classes=_float_or_none(measures.get("classes")),
            statements=_float_or_none(measures.get("statements")),
        ))

    for issue in (sonar_payload.get("issues") or {}).get("issues") or []:
        if not isinstance(issue, dict):
            continue
        if str(issue.get("status") or "").upper() == "CLOSED":
            continue
        text_range = issue.get("textRange") or {}
        db.add(SonarIssue(
            analysis_run_id=run.id,
            user_id=user_id,
            issue_key=issue.get("key"),
            file_path=_extract_file_path_from_component_or_issue(issue.get("component")),
            line=issue.get("line") or text_range.get("startLine"),
            type=issue.get("type"),
            severity=issue.get("severity"),
            rule=issue.get("rule"),
            message=issue.get("message"),
            status=issue.get("status"),
            raw_issue=issue,
        ))


def _issue_count_from_payload(sonar_payload: dict | None, issue_type: str) -> int:
    if not isinstance(sonar_payload, dict):
        return 0
    count = 0
    for issue in (sonar_payload.get("issues") or {}).get("issues") or []:
        if not isinstance(issue, dict):
            continue
        if str(issue.get("status") or "").upper() == "CLOSED":
            continue
        if str(issue.get("type") or "").upper() == issue_type.upper():
            count += 1
    return count


def _int_metric_or_issue_count(project_measures: dict, sonar_payload: dict | None, metric: str, issue_type: str) -> int | None:
    value = _float_or_none(project_measures.get(metric))
    if value is not None:
        return int(value)
    count = _issue_count_from_payload(sonar_payload, issue_type)
    return count if count else None


def _persist_contributor_analysis_summary(
    db: Session,
    run: AnalysisRun,
    user_id: int,
    sonar_result: dict,
    sonar_health_score: float | None,
    security_score: float | None,
    skill_score: float | None,
    contributor_login: str | None,
    touched_files: list[str] | None,
    included_files: list[str] | None,
) -> None:
    sonar_payload = sonar_result.get("sonar") if isinstance(sonar_result, dict) else None
    if not isinstance(sonar_payload, dict) or sonar_payload.get("error"):
        return

    project_measures = _extract_project_measures(sonar_payload)
    row = (
        db.query(ContributorAnalysisSummary)
        .filter(
            ContributorAnalysisSummary.analysis_run_id == run.id,
            ContributorAnalysisSummary.user_id == user_id,
        )
        .first()
    )
    if row is None:
        row = ContributorAnalysisSummary(
            analysis_run_id=run.id,
            repository_id=run.repository_id,
            user_id=user_id,
        )
        db.add(row)

    row.repository_id = run.repository_id
    row.contributor_login = contributor_login
    row.files_count = len(included_files or touched_files or [])
    row.touched_files = touched_files or included_files or []
    row.skill_score = skill_score
    row.sonar_health_score = sonar_health_score
    row.security_score = security_score
    row.coverage = _float_or_none(project_measures.get("coverage"))
    row.bugs = _int_metric_or_issue_count(project_measures, sonar_payload, "bugs", "BUG")
    row.code_smells = _int_metric_or_issue_count(project_measures, sonar_payload, "code_smells", "CODE_SMELL")
    row.duplicated_lines = _float_or_none(project_measures.get("duplicated_lines"))
    row.duplicated_lines_density = _float_or_none(project_measures.get("duplicated_lines_density"))
    row.complexity = _float_or_none(project_measures.get("complexity"))
    row.cognitive_complexity = _float_or_none(project_measures.get("cognitive_complexity"))
    row.ncloc = _float_or_none(project_measures.get("ncloc"))
    row.quality_gate = _extract_quality_gate(sonar_payload)
    row.measures = project_measures
    row.raw_payload = sonar_payload
    row.updated_at = datetime.now(timezone.utc)


def _prepare_repo_checkout(
    repo_url: str,
    branch: str,
    token: str,
    is_private: bool,
    repo_name: str,
    full_name: str,
) -> tuple[str, tempfile.TemporaryDirectory | None]:
    cache_root = os.environ.get("ANALYSIS_CACHE_DIR")
    auth_repo_url = repo_url
    if is_private and token:
        auth_repo_url = repo_url.replace("https://", f"https://x-access-token:{token}@")

    if cache_root:
        os.makedirs(cache_root, exist_ok=True)
        safe_name = full_name.replace("/", "__")
        clone_path = os.path.join(cache_root, safe_name)

        if os.path.isdir(os.path.join(clone_path, ".git")):
            subprocess.run(["git", "remote", "set-url", "origin", auth_repo_url], cwd=clone_path, check=True, timeout=300)
            subprocess.run(["git", "fetch", "--prune", "origin"], cwd=clone_path, check=True, timeout=300)
            subprocess.run(["git", "checkout", branch], cwd=clone_path, check=True, timeout=300)
            subprocess.run(["git", "reset", "--hard", f"origin/{branch}"], cwd=clone_path, check=True, timeout=300)
        else:
            clone_cmd = [
                "git", "clone", "--depth", "1", "--no-tags", "--filter=blob:none",
                "--branch", branch, "--single-branch", auth_repo_url, clone_path,
            ]
            subprocess.run(clone_cmd, check=True, timeout=300)

        return clone_path, None

    temp_dir = tempfile.TemporaryDirectory(prefix="repo_")
    clone_path = os.path.join(temp_dir.name, f"{repo_name}_{uuid.uuid4().hex}")
    clone_cmd = [
        "git", "clone", "--depth", "1", "--no-tags", "--filter=blob:none",
        "--branch", branch, "--single-branch", auth_repo_url, clone_path,
    ]
    subprocess.run(clone_cmd, check=True, timeout=300)
    return clone_path, temp_dir


async def resolve_github_identity(db: Session, user: User) -> tuple[str | None, str | None]:
    if not user.github_access_token:
        return None, None

    token = decrypt_github_token(user.github_access_token)
    if (
        user.github_token_expires_at
        and user.github_token_expires_at <= datetime.now(timezone.utc)
    ):
        refreshed_token = await refresh_github_access_token_for_user(db, user)
        if refreshed_token:
            token = refreshed_token

    github_user = await fetch_authenticated_github_user(token)
    github_login = github_user.get("login") if github_user else None
    return token, github_login


async def build_personal_repo_context(
    db: Session,
    user: User,
    repo,
    branch: str,
) -> dict:
    github_login = None
    if user.github_access_token:
        try:
            _, github_login = await resolve_github_identity(db, user)
        except Exception as exc:
            logging.warning(
                "Failed to resolve GitHub identity for user %s: %s",
                user.id,
                exc,
            )
    return {
        "has_github_identity": bool(github_login),
        "github_login": github_login,
        "is_private": bool(repo.is_private),
        "user_contributed": True,
        "commit_count_sample": 0,
        "latest_commit_at": None,
    }


def background_analysis_task(*args, **kwargs):
    return asyncio.run(_background_analysis_task_async(*args, **kwargs))


async def _background_analysis_task_async(
    run_id: int,
    repo_id: int,
    repo_url: str,
    repo_name: str,
    branch: str,
    full_name: str,
    token: str,
    is_private: bool,
    current_user_id: int,
    user_role: str,
    analysis_scope: str = "repository",
    contributor_login: str | None = None,
    touched_files: list[str] | None = None,
    manager_contributors: list[dict] | None = None,
    finalize_run: bool = True,
    generate_ai_insights: bool | None = None,
    coverage_report_path: str | None = None,
):
    is_recruiter_scoring_mode = user_role == "recruiter"
    if user_role == "manager" and analysis_scope == "team_contributions":
        return await _background_manager_team_analysis_task_async(
            run_id=run_id,
            repo_id=repo_id,
            repo_url=repo_url,
            repo_name=repo_name,
            branch=branch,
            full_name=full_name,
            token=token,
            is_private=is_private,
            manager_user_id=current_user_id,
            manager_contributors=manager_contributors or [],
        )

    skip_insights = is_recruiter_scoring_mode or generate_ai_insights is False
    logger.info(
        "[run=%s] Background analysis started repo=%s full_name=%s role=%s scope=%s mode=%s",
        run_id,
        repo_name,
        full_name,
        user_role,
        analysis_scope,
        "recruiter_scoring" if is_recruiter_scoring_mode else "developer_full",
    )
    db = SessionLocal()
    try:
        run = db.query(AnalysisRun).filter(AnalysisRun.id == run_id).first()
        if not run:
            logger.warning("[run=%s] Background analysis aborted: run not found", run_id)
            return

        clone_path = ""
        repo_context: tempfile.TemporaryDirectory | None = None
        sonar_result: dict = {}
        sonar_health_score: float | None = None
        included_sonar_files: list[str] | None = None
        try:
            logger.info("[run=%s] Git checkout started branch=%s private=%s", run_id, branch, is_private)
            clone_path, repo_context = _prepare_repo_checkout(
                repo_url=repo_url,
                branch=branch,
                token=token,
                is_private=is_private,
                repo_name=repo_name,
                full_name=full_name,
            )
            logger.info("[run=%s] Git checkout finished", run_id)

            if analysis_scope == "contribution":
                included_sonar_files = _existing_python_contribution_files(clone_path, touched_files)
                if not included_sonar_files:
                    raise Exception("No existing Python contribution files were found for this repository branch.")
                logger.info(
                    "[run=%s] Contribution Sonar file scope resolved count=%d",
                    run_id,
                    len(included_sonar_files),
                )

            run_sonar_for_scope = finalize_run or analysis_scope == "contribution"
            if run_sonar_for_scope:
                try:
                    logger.info(
                        "[run=%s] SonarQube analysis started scope=%s finalize_run=%s",
                        run_id,
                        analysis_scope,
                        finalize_run,
                    )
                    sonar_result = run_sonar_analysis(
                        repo_path=clone_path,
                        full_name=full_name,
                        branch=branch,
                        coverage_report_path=coverage_report_path,
                        included_files=included_sonar_files,
                    )
                    sonar_health_score = compute_sonar_health_score(sonar_result.get("sonar"))
                    if analysis_scope == "contribution":
                        _persist_contributor_sonar_detail_rows(
                            db,
                            run,
                            current_user_id,
                            sonar_result,
                        )
                    else:
                        _persist_sonar_results(
                            db,
                            run,
                            current_user_id,
                            sonar_result,
                            sonar_health_score,
                        )
                    logger.info("[run=%s] SonarQube analysis finished", run_id)
                except Exception as exc:
                    logger.exception("[run=%s] SonarQube analysis failed: %s", run_id, exc)
                    sonar_result = {
                        "source": "sonarqube",
                        "project_key": None,
                        "sonar": {
                            "error": str(exc),
                        },
                    }
                    sonar_health_score = None

            python_files = read_local_repo_files(clone_path)
            if analysis_scope == "contribution":
                touched_set = set(included_sonar_files or [])
                python_files = [
                    f for f in python_files
                    if f.get("path", "").replace("\\", "/") in touched_set
                ]
                if not python_files:
                    raise Exception("No Python files were found in your contributions for this repository.")

            total_source_chars = sum(len(file_obj.get("content", "") or "") for file_obj in python_files)
            llm_payload_chars = sum(
                len("\n".join((file_obj.get("content", "") or "").splitlines()[:300]))
                for file_obj in python_files
            )
            logger.info(
                "[run=%s] Files selected for analysis count=%d source_chars=%d llm_input_chars_approx=%d",
                run_id,
                len(python_files),
                total_source_chars,
                llm_payload_chars,
            )
            if not python_files:
                raise Exception("No Python files were found for analysis.")

            logger.info("[run=%s] Security analysis started", run_id)
            pipeline_result = run_security_analysis(clone_path)
            logger.info(
                "[run=%s] Security analysis finished findings=%d failed_tools=%s",
                run_id,
                len(pipeline_result.get("findings", [])),
                pipeline_result.get("failed_tools", []),
            )

            llm_result = {}

            logger.info("[run=%s] Repository metrics extraction started", run_id)
            analysis_result = analyze_python_files(python_files)
            logger.info(
                "[run=%s] Repository metrics extraction finished files=%d",
                run_id,
                len(analysis_result.get("files", [])),
            )
            code_intelligence_result = analysis_result
            final_scores = {}

            try:
                unified = build_unified_schema(code_intelligence_result, llm_result, run.commit_sha)
                code_intelligence_result.setdefault("unified_metrics", {})
                code_intelligence_result["unified_metrics"] = unified
            except Exception:
                logger.exception("[run=%s] Failed to build unified metrics schema", run_id)

            findings = pipeline_result.get("findings", [])
            failed_tools = pipeline_result.get("failed_tools", [])
        finally:
            if repo_context:
                repo_context.cleanup()

        ignored = ["venv", ".venv", "__pycache__", "migrations"]
        findings = [
            f for f in findings
            if not any(p in f.get("file_path", "") for p in ignored)
        ]
        if analysis_scope == "contribution":
            touched_set = {p.replace("\\", "/") for p in (touched_files or [])}
            findings = [
                f for f in findings
                if f.get("file_path", "").replace("\\", "/") in touched_set
            ]

        for finding in findings:
            try:
                validated = FindingModel(**finding)
            except Exception:
                continue

            db.add(SecurityFinding(
                analysis_run_id=run.id,
                user_id=current_user_id,
                tool=validated.tool,
                rule=validated.rule,
                cwe=validated.cwe,
                file_path=validated.file_path,
                severity=validated.severity,
                description=validated.description,
                line_number=validated.line_number,
                owasp_category=validated.owasp_category,
            ))

        for file_report in code_intelligence_result.get("files", []):
            metrics = file_report.get("metrics", {})
            maintainability_index = max(
                0.0,
                min(100.0, float(metrics.get("maintainability_index", 0.0) or 0.0)),
            )

            db.add(CodeMetrics(
                analysis_run_id=run.id,
                user_id=current_user_id,
                file_path=file_report.get("path"),
                cyclomatic_complexity=float(metrics.get("cyclomatic_complexity", 0.0) or 0.0),
                lines_of_code=int(metrics.get("loc", 0) or 0),
                duplication_score=float(metrics.get("duplication_score", 0.0) or 0.0),
                maintainability_index=maintainability_index,
                raw_metrics=metrics,
            ))

        total_loc = code_intelligence_result.get("aggregate_metrics", {}).get("total_loc")
        if total_loc is None:
            total_loc = code_intelligence_result.get("aggregate_metrics", {}).get("loc", 1000)
        security_score_breakdown = compute_security_score_breakdown(findings, int(total_loc or 0))
        security_score = security_score_breakdown["overall"]
        overall_score = compute_skill_score_engine(
            sonar_health_score=sonar_health_score,
            security_score=security_score,
        )
        if analysis_scope == "contribution":
            _persist_contributor_analysis_summary(
                db=db,
                run=run,
                user_id=current_user_id,
                sonar_result=sonar_result,
                sonar_health_score=sonar_health_score,
                security_score=security_score,
                skill_score=overall_score,
                contributor_login=contributor_login,
                touched_files=touched_files,
                included_files=included_sonar_files,
            )

        logger.info(
            "[run=%s] Final scores before DB save role=%s scope=%s scores=%s security_score=%.2f",
            run_id,
            user_role,
            analysis_scope,
            final_scores,
            security_score,
        )
        db.add(SkillScore(
            analysis_run_id=run.id,
            user_id=current_user_id,
            code_quality_score=None,
            maintainability_score=None,
            architecture_score=None,
            security_awareness_score=security_score,
            problem_solving_score=None,
            overall_score=overall_score,
            sonar_health_score=sonar_health_score,
        ))
        db.commit()
        logger.info("[run=%s] SkillScore DB save successful", run_id)

        if is_recruiter_scoring_mode:
            ai_insights = {
                "score_only": True,
                "failed_tools": failed_tools,
            }
        else:
            ai_insights = {
                "failed_tools": failed_tools,
            }

        if sonar_result:
            ai_insights["source"] = "sonarqube"
            ai_insights["project_key"] = sonar_result.get("project_key")
            ai_insights["sonar"] = sonar_result.get("sonar", {})

        if not skip_insights:
            sonar_metrics = {}
            sonar_issues = []
            security_gap_findings = []
            try:
                sonar_payload = sonar_result.get("sonar") if isinstance(sonar_result, dict) else None
                sonar_metrics, sonar_file_metrics, sonar_issues, security_gap_findings = _sonar_skill_gap_inputs(
                    sonar_payload,
                    findings,
                )
                ai_insights["llm_skill_gaps"] = analyze_skill_gaps_with_llm(
                    sonar_metrics=sonar_metrics,
                    sonar_file_metrics=sonar_file_metrics,
                    sonar_issues=sonar_issues,
                    security_findings=security_gap_findings,
                )
            except Exception:
                logger.exception("[run=%s] LLM skill gap analysis failed", run_id)
                ai_insights["llm_skill_gaps"] = {"skill_gaps": []}

            logger.info("[run=%s] Developer insight generation started", run_id)
            try:
                score_row = (
                    db.query(SkillScore)
                    .filter(
                        SkillScore.analysis_run_id == run.id,
                        SkillScore.user_id == current_user_id,
                    )
                    .first()
                )
                metric_rows = db.query(CodeMetrics).filter(CodeMetrics.analysis_run_id == run.id).all()
                findings_rows = db.query(SecurityFinding).filter(SecurityFinding.analysis_run_id == run.id).all()
                if score_row:
                    llm_skill_gaps = ai_insights.get("llm_skill_gaps") if isinstance(ai_insights, dict) else {}
                    detected_skill_gaps = []
                    if isinstance(llm_skill_gaps, dict) and isinstance(llm_skill_gaps.get("skill_gaps"), list):
                        detected_skill_gaps = [
                            gap for gap in llm_skill_gaps.get("skill_gaps") or []
                            if isinstance(gap, dict)
                        ]
                    ai_insights["learning_recommendations"] = build_learning_recommendations(
                        run,
                        score_row,
                        metric_rows,
                        findings_rows,
                        sonar_metrics=sonar_metrics,
                        sonar_issues=sonar_issues,
                        detected_skill_gaps=detected_skill_gaps,
                    )
            except Exception:
                logger.exception("[run=%s] Learning recommendations generation failed", run_id)
            try:
                security_report = {
                    "total_findings": len(findings),
                    "severity_distribution": {},
                    "owasp_distribution": {},
                    "top_vulnerable_files": {},
                }
                file_counts = {}
                for finding in findings:
                    sev = finding.get("severity") or "UNKNOWN"
                    security_report["severity_distribution"][sev] = security_report["severity_distribution"].get(sev, 0) + 1
                    cat = finding.get("owasp_category") or "Unknown"
                    security_report["owasp_distribution"][cat] = security_report["owasp_distribution"].get(cat, 0) + 1
                    fp = finding.get("file_path") or "unknown"
                    file_counts[fp] = file_counts.get(fp, 0) + 1

                security_report["top_vulnerable_files"] = dict(sorted(file_counts.items(), key=lambda x: x[1], reverse=True)[:5])
                security_report["categorized_findings"] = group_findings_by_severity_and_file(findings)
                security_report["security_score"] = security_score
                security_report["security_score_breakdown"] = security_score_breakdown
                security_report["failed_tools"] = failed_tools
                ai_insights["security_report"] = security_report

                analysis_payload = {
                    "scores": final_scores,
                    "aggregate_metrics": code_intelligence_result.get("aggregate_metrics", {}),
                }

                guidance = await generate_insights(
                    role=user_role,
                    analysis_result=analysis_payload,
                    security_report=security_report,
                    doc_id=STANDARDS_DOC_ID,
                )
                if isinstance(guidance, dict):
                    ai_insights.update(guidance)
                ai_insights.pop("skills_insights", None)
            except Exception:
                logger.exception("[run=%s] AI insights generation failed", run_id)

            logger.info("[run=%s] Developer insight generation finished", run_id)
        else:
            logger.info(
                "[run=%s] Insight generation skipped role=%s finalize_run=%s",
                run_id,
                user_role,
                finalize_run,
            )

        if finalize_run:
            run.ai_insights = ai_insights
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            repo_analysis = (
                db.query(RepositoryAnalysis)
                .filter(RepositoryAnalysis.last_run_id == run.id)
                .first()
            )
            if repo_analysis:
                repo_analysis.analysis_status = "completed"
                repo_analysis.analyzed_at = run.completed_at
            db.commit()
            logger.info("[run=%s] Background analysis completed successfully", run_id)
        else:
            logger.info(
                "[run=%s] Contributor score completed user_id=%s without finalizing run",
                run_id,
                current_user_id,
            )
        return {
            "status": "completed",
            "run_id": run_id,
            "score_user_id": current_user_id,
        }

    except LLMError as exc:
        error_text = str(exc)
        logger.exception("[run=%s] LLM error in background task", run_id)
        db.rollback()

        run = db.query(AnalysisRun).filter(AnalysisRun.id == run_id).first()
        if run and finalize_run:
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            run.ai_insights = {
                "error_reason": "llm_failed",
                "error_message": error_text,
            }
            repo_analysis = (
                db.query(RepositoryAnalysis)
                .filter(RepositoryAnalysis.last_run_id == run.id)
                .first()
            )
            if repo_analysis:
                repo_analysis.analysis_status = "failed"
                repo_analysis.analyzed_at = run.completed_at
            db.commit()
            logger.info("[run=%s] Failure status persisted after LLM error", run_id)
        return {
            "status": "failed",
            "run_id": run_id,
            "score_user_id": current_user_id,
            "error_reason": "llm_failed",
            "error_message": error_text,
        }
    except Exception as exc:
        error_text = str(exc)
        logger.exception("[run=%s] Background task error", run_id)
        db.rollback()

        run = db.query(AnalysisRun).filter(AnalysisRun.id == run_id).first()
        error_reason = "unknown"
        if run and finalize_run:
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            if "rate" in error_text.lower():
                error_reason = "rate_limit"
                run.ai_insights = {"error_reason": "rate_limit", "error_message": error_text}
            elif "not found" in error_text.lower():
                error_reason = "not_found"
                run.ai_insights = {"error_reason": "not_found", "error_message": error_text}
            else:
                run.ai_insights = {"error_reason": "unknown", "error_message": error_text}
            repo_analysis = (
                db.query(RepositoryAnalysis)
                .filter(RepositoryAnalysis.last_run_id == run.id)
                .first()
            )
            if repo_analysis:
                repo_analysis.analysis_status = "failed"
                repo_analysis.analyzed_at = run.completed_at
            db.commit()
            logger.info("[run=%s] Failure status persisted after background task error", run_id)
        elif "rate" in error_text.lower():
            error_reason = "rate_limit"
        elif "not found" in error_text.lower():
            error_reason = "not_found"
        return {
            "status": "failed",
            "run_id": run_id,
            "score_user_id": current_user_id,
            "error_reason": error_reason,
            "error_message": error_text,
        }
    finally:
        db.close()


def background_manager_team_analysis_task(*args, **kwargs):
    return asyncio.run(_background_manager_team_analysis_task_async(*args, **kwargs))


async def _background_manager_team_analysis_task_async(
    run_id: int,
    repo_id: int,
    repo_url: str,
    repo_name: str,
    branch: str,
    full_name: str,
    token: str,
    is_private: bool,
    manager_user_id: int,
    manager_contributors: list[dict],
):
    logger.info(
        "[run=%s] Manager team analysis started contributors=%d",
        run_id,
        len(manager_contributors),
    )
    completed: list[dict] = []
    failed: list[dict] = []

    for contributor in manager_contributors:
        try:
            developer_id = int(contributor.get("user_id"))
        except (TypeError, ValueError):
            failed.append({
                "user_id": contributor.get("user_id"),
                "error_reason": "invalid_contributor",
                "error_message": "Contributor payload did not include a valid user_id.",
            })
            continue

        contributor_files = contributor.get("touched_files") or []
        if not contributor_files:
            failed.append({
                "user_id": developer_id,
                "error_reason": "no_touched_files",
                "error_message": "Contributor payload did not include touched files.",
            })
            continue

        result = await _background_analysis_task_async(
            run_id=run_id,
            repo_id=repo_id,
            repo_url=repo_url,
            repo_name=repo_name,
            branch=branch,
            full_name=full_name,
            token=token,
            is_private=is_private,
            current_user_id=developer_id,
            user_role="developer",
            analysis_scope="contribution",
            contributor_login=contributor.get("contributor_login"),
            touched_files=contributor_files,
            finalize_run=False,
            generate_ai_insights=False,
        )

        result = result or {}
        if result.get("status") == "completed":
            completed.append({
                "user_id": developer_id,
                "contributor_login": contributor.get("contributor_login"),
                "touched_file_count": len(contributor_files),
            })
        else:
            failed.append({
                "user_id": developer_id,
                "contributor_login": contributor.get("contributor_login"),
                "error_reason": result.get("error_reason") or "analysis_failed",
                "error_message": result.get("error_message") or "Contributor analysis failed.",
            })

    db = SessionLocal()
    try:
        run = db.query(AnalysisRun).filter(AnalysisRun.id == run_id).first()
        if not run:
            logger.warning("[run=%s] Manager team analysis could not finalize: run not found", run_id)
            return {
                "status": "failed",
                "run_id": run_id,
                "error_reason": "run_not_found",
            }

        score_count = (
            db.query(ContributorAnalysisSummary)
            .filter(ContributorAnalysisSummary.analysis_run_id == run_id)
            .count()
        )
        run.completed_at = datetime.now(timezone.utc)
        run.status = "completed" if score_count else "failed"
        db.flush()
        if run.status == "completed":
            manager_user = db.query(User).filter(User.id == manager_user_id).first()
            repo_score_rows = (
                db.query(ContributorAnalysisSummary, AnalysisRun, Repository, User)
                .join(AnalysisRun, ContributorAnalysisSummary.analysis_run_id == AnalysisRun.id)
                .join(Repository, AnalysisRun.repository_id == Repository.id)
                .join(User, ContributorAnalysisSummary.user_id == User.id)
                .filter(
                    ContributorAnalysisSummary.analysis_run_id == run_id,
                    User.role == UserRole.developer,
                )
                .all()
            )

            try:
                repo_insights = await _generate_manager_dashboard_insights_from_rows(
                    repo_score_rows,
                    db,
                    manager_user_id,
                    f"run:{run_id}",
                )
                if repo_insights is not None:
                    run.ai_insights = repo_insights
                    logger.info(
                        "[run=%s] Saved repo-specific manager team insights manager_user_id=%s",
                        run_id,
                        manager_user_id,
                    )
            except Exception:
                logger.exception(
                    "[run=%s] Repo-specific manager team insight generation failed manager_user_id=%s",
                    run_id,
                    manager_user_id,
                )

            try:
                if manager_user:
                    global_rows = _query_manager_score_rows(db, manager_user_id)
                    global_insights = await _generate_manager_dashboard_insights_from_rows(
                        global_rows,
                        db,
                        manager_user_id,
                        "global",
                    )
                    if global_insights is not None:
                        manager_user.global_team_insights = _merge_preserved_member_details(
                            manager_user.global_team_insights,
                            global_insights,
                        )
                        flag_modified(manager_user, "global_team_insights")
                        logger.info(
                            "[run=%s] Saved global manager team insights manager_user_id=%s",
                            run_id,
                            manager_user_id,
                        )

                    if global_rows:
                        rows_by_member: dict[int, list] = {}
                        for row in global_rows:
                            rows_by_member.setdefault(row[3].id, []).append(row)
                        for member_rows in rows_by_member.values():
                            try:
                                await _generate_and_store_member_detail_insights_from_rows(
                                    db,
                                    manager_user,
                                    member_rows,
                                )
                            except Exception:
                                logger.exception(
                                    "[run=%s] Manager member detail insight generation failed manager_user_id=%s member_user_id=%s",
                                    run_id,
                                    manager_user_id,
                                    member_rows[0][3].id if member_rows else None,
                                )
            except Exception:
                logger.exception(
                    "[run=%s] Global manager team insight generation failed manager_user_id=%s",
                    run_id,
                    manager_user_id,
                )
        logger.info(
            "[run=%s] Manager team execution summary manager_user_id=%s requested=%d analyzed=%d failed=%d completed=%s failed_details=%s",
            run_id,
            manager_user_id,
            len(manager_contributors),
            len(completed),
            len(failed),
            completed,
            failed,
        )

        repo_analysis = (
            db.query(RepositoryAnalysis)
            .filter(RepositoryAnalysis.last_run_id == run.id)
            .first()
        )
        if repo_analysis:
            repo_analysis.analysis_status = run.status
            repo_analysis.analyzed_at = run.completed_at

        db.commit()
        logger.info(
            "[run=%s] Manager team analysis finalized status=%s scores=%d completed=%d failed=%d",
            run_id,
            run.status,
            score_count,
            len(completed),
            len(failed),
        )
        return {
            "status": run.status,
            "run_id": run_id,
            "contributors_analyzed": len(completed),
            "contributors_failed": len(failed),
        }
    finally:
        db.close()


async def _run_manager_contributor_analysis_after_repository(
    repository_run_id: int,
    repo_id: int,
    repo_url: str,
    repo_name: str,
    branch: str,
    full_name: str,
    token: str | None,
    is_private: bool,
    manager_user_id: int,
):
    db = SessionLocal()
    try:
        repository_run = (
            db.query(AnalysisRun)
            .filter(
                AnalysisRun.id == repository_run_id,
                AnalysisRun.user_id == manager_user_id,
                AnalysisRun.analysis_scope == "repository",
            )
            .first()
        )
        if not repository_run or repository_run.status != "completed":
            logger.info(
                "[run=%s] Skipping manager contributor analysis because repository run is not completed",
                repository_run_id,
            )
            return

        existing_team_run = (
            db.query(AnalysisRun)
            .filter(
                AnalysisRun.repository_id == repo_id,
                AnalysisRun.user_id == manager_user_id,
                AnalysisRun.branch == branch,
                AnalysisRun.commit_sha == repository_run.commit_sha,
                AnalysisRun.analysis_scope == "team_contributions",
                AnalysisRun.status.in_(["running", "completed"]),
            )
            .order_by(AnalysisRun.triggered_at.desc())
            .first()
        )
        if existing_team_run:
            logger.info(
                "[run=%s] Skipping manager contributor analysis because team run %s already exists with status=%s",
                repository_run_id,
                existing_team_run.id,
                existing_team_run.status,
            )
            return

        registered_developers = (
            db.query(User)
            .filter(User.role == UserRole.developer)
            .all()
        )
    finally:
        db.close()

    try:
        commit_records = await fetch_repository_commit_contributions(
            token,
            full_name,
            branch,
        )
    except Exception:
        logger.exception(
            "[run=%s] Manager contributor discovery failed; repository analysis remains completed",
            repository_run_id,
        )
        return

    manager_contributors = _build_manager_contributor_scopes(
        registered_developers,
        commit_records,
    )
    if not manager_contributors:
        logger.info(
            "[run=%s] Manager contributor analysis skipped: no registered developers with Python contributions",
            repository_run_id,
        )
        return

    db = SessionLocal()
    try:
        _link_repository_contributors(db, repo_id, manager_contributors)
        team_run = AnalysisRun(
            repository_id=repo_id,
            user_id=manager_user_id,
            branch=branch,
            commit_sha=(
                db.query(AnalysisRun.commit_sha)
                .filter(AnalysisRun.id == repository_run_id)
                .scalar()
            ),
            analysis_scope="team_contributions",
            contributor_login=None,
            status="running",
            triggered_at=datetime.now(timezone.utc),
        )
        db.add(team_run)
        db.commit()
        db.refresh(team_run)
        team_run_id = team_run.id
    finally:
        db.close()

    try:
        await _background_manager_team_analysis_task_async(
            run_id=team_run_id,
            repo_id=repo_id,
            repo_url=repo_url,
            repo_name=repo_name,
            branch=branch,
            full_name=full_name,
            token=token,
            is_private=is_private,
            manager_user_id=manager_user_id,
            manager_contributors=manager_contributors,
        )
    except Exception:
        logger.exception(
            "[run=%s] Manager contributor analysis failed; repository run remains completed",
            repository_run_id,
        )
        db = SessionLocal()
        try:
            team_run = db.query(AnalysisRun).filter(AnalysisRun.id == team_run_id).first()
            if team_run and team_run.status != "completed":
                team_run.status = "failed"
                team_run.completed_at = datetime.now(timezone.utc)
                db.commit()
        finally:
            db.close()


async def _background_manager_repository_analysis_task_async(
    run_id: int,
    repo_id: int,
    repo_url: str,
    repo_name: str,
    branch: str,
    full_name: str,
    token: str | None,
    is_private: bool,
    manager_user_id: int,
    coverage_report_path: str | None = None,
):
    result = await _background_analysis_task_async(
        run_id=run_id,
        repo_id=repo_id,
        repo_url=repo_url,
        repo_name=repo_name,
        branch=branch,
        full_name=full_name,
        token=token,
        is_private=is_private,
        current_user_id=manager_user_id,
        user_role="manager",
        analysis_scope="repository",
        contributor_login=None,
        touched_files=[],
        finalize_run=True,
        coverage_report_path=coverage_report_path,
    )

    if (result or {}).get("status") == "completed":
        await _run_manager_contributor_analysis_after_repository(
            repository_run_id=run_id,
            repo_id=repo_id,
            repo_url=repo_url,
            repo_name=repo_name,
            branch=branch,
            full_name=full_name,
            token=token,
            is_private=is_private,
            manager_user_id=manager_user_id,
        )
    return result


def background_manager_repository_analysis_task(*args, **kwargs):
    return asyncio.run(_background_manager_repository_analysis_task_async(*args, **kwargs))


def background_manager_contributor_analysis_task(*args, **kwargs):
    return asyncio.run(_run_manager_contributor_analysis_after_repository(*args, **kwargs))


def run_background_analysis_task(*args, **kwargs):
    asyncio.run(background_analysis_task(*args, **kwargs))
