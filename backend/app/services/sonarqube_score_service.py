from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, CodeMetrics


ALLOWED_ISSUE_TYPES = {"BUG", "CODE_SMELL"}


def compute_skill_score_engine(sonar_health_score, security_score):
    if sonar_health_score is None or security_score is None:
        return None
    return round((0.70 * float(sonar_health_score)) + (0.30 * float(security_score)), 2)


def classify_skill_score(score):
    if score is None:
        return "Unavailable"
    if score >= 90:
        return "Excellent"
    if score >= 80:
        return "Very Good"
    if score >= 70:
        return "Good"
    if score >= 60:
        return "Fair"
    return "Needs Improvement"


def build_skill_score_fields(
    skill_score_row: Any | None,
    sonar_health_score: Any | None = None,
    security_score: Any | None = None,
) -> dict[str, Any]:
    score = _coerce_number(getattr(skill_score_row, "overall_score", None))
    if score is None:
        score = compute_skill_score_engine(
            sonar_health_score=(
                sonar_health_score
                if sonar_health_score is not None
                else getattr(skill_score_row, "sonar_health_score", None)
            ),
            security_score=(
                security_score
                if security_score is not None
                else getattr(skill_score_row, "security_awareness_score", None)
            ),
        )
    return {
        "skill_score": score,
        "skill_score_level": classify_skill_score(score),
    }


def get_sonar_payload(run: AnalysisRun) -> dict[str, Any] | None:
    ai_insights = run.ai_insights or {}
    if not isinstance(ai_insights, dict):
        return None
    payload = ai_insights.get("sonar")
    if not isinstance(payload, dict) or not payload or payload.get("error"):
        return None
    return payload


def get_sonar_measure_map(sonar_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(sonar_payload, dict):
        return {}
    measures = ((sonar_payload.get("measures") or {}).get("component") or {}).get("measures") or []
    return {
        item.get("metric"): item.get("value")
        for item in measures
        if isinstance(item, dict) and item.get("metric")
    }


def get_sonar_file_measure_map(sonar_payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(sonar_payload, dict):
        return {}
    components = (sonar_payload.get("file_measures") or {}).get("components") or []
    file_measures: dict[str, dict[str, Any]] = {}
    for component in components:
        if not isinstance(component, dict):
            continue
        path = component.get("path") or component.get("name")
        if not path and component.get("key"):
            path = str(component["key"]).rsplit(":", 1)[-1]
        if not path:
            continue
        file_measures[str(path).replace("\\", "/")] = {
            item.get("metric"): item.get("value")
            for item in component.get("measures") or []
            if isinstance(item, dict) and item.get("metric")
        }
    return file_measures


def get_sonar_quality_gate_status(sonar_payload: dict[str, Any] | None) -> str | None:
    if not isinstance(sonar_payload, dict):
        return None
    status = ((sonar_payload.get("quality_gate") or {}).get("projectStatus") or {}).get("status")
    return str(status).upper() if status else None


def get_coverage_metadata(sonar_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(sonar_payload, dict):
        return {
            "status": "unavailable",
            "available": False,
            "reason": "sonar_unavailable",
            "source": None,
        }
    metadata = sonar_payload.get("coverage")
    if not isinstance(metadata, dict):
        return {
            "status": "unknown",
            "available": True,
            "reason": None,
            "source": "sonar",
        }
    status = str(metadata.get("status") or "unavailable")
    available = status in {"ready", "ready_with_test_failures"} and bool(metadata.get("coverage_file_exists"))
    return {
        **metadata,
        "status": status,
        "available": available,
        "reason": metadata.get("reason") if not available else None,
        "source": metadata.get("source"),
    }


def get_sonar_issues(sonar_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(sonar_payload, dict):
        return []
    raw_issues = (sonar_payload.get("issues") or {}).get("issues") or []
    return [
        issue
        for issue in raw_issues
        if isinstance(issue, dict) and str(issue.get("type", "")).upper() in ALLOWED_ISSUE_TYPES
    ]


def _float_measure(measures: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = measures.get(key)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _number_measure(measures: dict[str, Any], key: str, default: float | int = 0) -> float | int:
    numeric = _float_measure(measures, key, float(default))
    return int(numeric) if float(numeric).is_integer() else numeric


def _duration_seconds(run: AnalysisRun) -> int | None:
    if not run.completed_at or not run.triggered_at:
        return None
    return int(
        (run.completed_at - run.triggered_at).total_seconds()
    )


def _repository_payload(run: AnalysisRun) -> dict[str, Any]:
    return {
        "name": run.repository.name,
        "full_name": run.repository.full_name,
        "branch": run.branch,
        "analysis_date": run.completed_at or run.triggered_at,
        "duration_seconds": _duration_seconds(run),
    }


def _raw_metrics(row: CodeMetrics) -> dict[str, Any]:
    return row.raw_metrics if isinstance(row.raw_metrics, dict) else {}


def _coerce_number(value: Any) -> float | int | None:
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


def _numeric_raw_metric(raw_metrics: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = _coerce_number(raw_metrics.get(key))
        if value is not None:
            return value
    return None


def _numeric_measure_value(measures: dict[str, Any], key: str) -> Any:
    return _coerce_number(measures.get(key))


def _first_number(*values: Any) -> Any:
    for value in values:
        numeric = _coerce_number(value)
        if numeric is not None:
            return numeric
    return None


def _first_skill_score(run: AnalysisRun) -> Any | None:
    scores = getattr(run, "skill_scores", None) or []
    return scores[0] if scores else None


def _normalize_file_path(value: Any) -> str:
    if value is None:
        return ""
    path = str(value).replace("\\", "/").strip()
    if ":" in path:
        path = path.rsplit(":", 1)[-1]
    return path.lstrip("/")


def _valid_analysis_files(metric_rows: list[CodeMetrics]) -> set[str]:
    return {
        normalized
        for row in metric_rows
        for normalized in [_normalize_file_path(row.file_path)]
        if normalized
    }


def _file_matches_analysis(path: Any, valid_files: set[str]) -> bool:
    if not valid_files:
        return True
    normalized = _normalize_file_path(path)
    if not normalized:
        return False
    if normalized in valid_files:
        return True
    return any(
        normalized.endswith(f"/{valid}")
        or valid.endswith(f"/{normalized}")
        for valid in valid_files
    )


def _filter_sonar_file_measures_for_analysis(
    sonar_file_measures: dict[str, dict[str, Any]],
    valid_files: set[str],
) -> dict[str, dict[str, Any]]:
    return {
        _normalize_file_path(path): measures
        for path, measures in sonar_file_measures.items()
        if _normalize_file_path(path) and _file_matches_analysis(path, valid_files)
    }


def _filter_issues_for_analysis(
    issues: list[dict[str, Any]],
    valid_files: set[str],
) -> list[dict[str, Any]]:
    if not valid_files:
        return issues
    return [
        issue
        for issue in issues
        if _file_matches_analysis(issue.get("file"), valid_files)
    ]


def _build_file_metrics(
    metric_rows: list[CodeMetrics],
    sonar_file_measures: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    file_metrics = []
    sonar_file_measures = sonar_file_measures or {}
    seen_files: set[str] = set()
    for row in metric_rows:
        raw_metrics = _raw_metrics(row)
        file_path = _normalize_file_path(row.file_path)
        sonar_metrics = sonar_file_measures.get(file_path, {})
        seen_files.add(file_path)
        file_metrics.append(
            {
                "file": row.file_path,
                "lines_of_code": row.lines_of_code,
                "complexity": row.cyclomatic_complexity,
                "duplication": row.duplication_score,
                "coverage": _first_number(
                    _numeric_measure_value(sonar_metrics, "coverage"),
                    _numeric_raw_metric(raw_metrics, "coverage"),
                ),
                "duplicated_lines": _first_number(
                    _numeric_measure_value(sonar_metrics, "duplicated_lines"),
                    _numeric_raw_metric(raw_metrics, "duplicated_lines"),
                ),
                "functions": _first_number(
                    _numeric_measure_value(sonar_metrics, "functions"),
                    _numeric_raw_metric(raw_metrics, "functions", "function_count"),
                ),
            }
        )
    for file_path, sonar_metrics in sonar_file_measures.items():
        if file_path in seen_files:
            continue
        file_metrics.append(
            {
                "file": file_path,
                "lines_of_code": None,
                "complexity": None,
                "duplication": None,
                "coverage": _numeric_measure_value(sonar_metrics, "coverage"),
                "duplicated_lines": _numeric_measure_value(sonar_metrics, "duplicated_lines"),
                "functions": _numeric_measure_value(sonar_metrics, "functions"),
            }
        )
    return file_metrics


def _extract_function_complexities(raw_metrics: dict[str, Any]) -> list[dict[str, Any]]:
    raw_functions = raw_metrics.get("function_complexities")
    if not isinstance(raw_functions, list):
        raw_functions = raw_metrics.get("functions")
    if not isinstance(raw_functions, list):
        return []

    functions = []
    for item in raw_functions:
        if not isinstance(item, dict):
            continue
        name = item.get("function") or item.get("name")
        complexity = item.get("complexity")
        if complexity is None:
            complexity = item.get("cyclomatic")
        complexity = _coerce_number(complexity)
        if not name or complexity is None:
            continue
        functions.append(
            {
                "function": name,
                "complexity": complexity,
            }
        )
    return functions


def _build_complex_functions(metric_rows: list[CodeMetrics]) -> list[dict[str, Any]]:
    complex_functions = []
    for row in metric_rows:
        for function in _extract_function_complexities(_raw_metrics(row)):
            complex_functions.append(
                {
                    "function": function["function"],
                    "file": row.file_path,
                    "complexity": function["complexity"],
                }
            )

    return sorted(
        complex_functions,
        key=lambda item: float(item["complexity"] or 0),
        reverse=True,
    )


def compute_sonar_health_score(sonar_payload: dict[str, Any] | None) -> float | None:
    if not isinstance(sonar_payload, dict) or not sonar_payload or sonar_payload.get("error"):
        return None

    measures = get_sonar_measure_map(sonar_payload)
    gate_status = get_sonar_quality_gate_status(sonar_payload)
    if not measures and gate_status is None:
        return None

    penalties = 0.0
    if gate_status == "ERROR":
        penalties += 20
    elif gate_status == "WARN":
        penalties += 5

    penalties += min(_float_measure(measures, "bugs") * 2, 20)
    penalties += min(_float_measure(measures, "code_smells") * 0.5, 15)
    coverage_meta = get_coverage_metadata(sonar_payload)
    if coverage_meta.get("available"):
        penalties += min((100 - _float_measure(measures, "coverage", 0.0)) * 0.15, 15)
    penalties += min(_float_measure(measures, "duplicated_lines_density") * 0.5, 10)
    penalties += min(max(0.0, _float_measure(measures, "complexity") - 50) * 0.1, 10)
    penalties += min(max(0.0, _float_measure(measures, "cognitive_complexity") - 50) * 0.1, 10)

    return round(max(0.0, min(100.0, 100.0 - penalties)), 2)


def _issue_file(component: str | None) -> str | None:
    if not component:
        return None
    return component.rsplit(":", 1)[1] if ":" in component else component


def _issue_item(issue: dict[str, Any]) -> dict[str, Any]:
    text_range = issue.get("textRange") or {}
    return {
        "type": issue.get("type"),
        "severity": issue.get("severity"),
        "file": _issue_file(issue.get("component")),
        "line": issue.get("line") or text_range.get("startLine"),
        "message": issue.get("message"),
    }


def build_sonar_repo_summary(run: AnalysisRun) -> dict[str, Any]:
    sonar_payload = get_sonar_payload(run)
    measures = get_sonar_measure_map(sonar_payload)
    quality_gate = get_sonar_quality_gate_status(sonar_payload)
    score = compute_sonar_health_score(sonar_payload)
    skill_score_row = _first_skill_score(run)
    skill_score_fields = build_skill_score_fields(
        skill_score_row,
        sonar_health_score=score,
        security_score=getattr(skill_score_row, "security_awareness_score", None),
    )
    coverage_meta = get_coverage_metadata(sonar_payload)
    coverage_value = _number_measure(measures, "coverage") if sonar_payload and coverage_meta.get("available") else None

    return {
        **skill_score_fields,
        "sonar_health_score": score,
        "sonar_state": "ready" if score is not None else "sonar_unavailable",
        "quality_gate": quality_gate,
        "bugs": _number_measure(measures, "bugs") if sonar_payload else None,
        "code_smells": _number_measure(measures, "code_smells") if sonar_payload else None,
        "coverage": coverage_value,
        "coverage_available": bool(coverage_meta.get("available")),
        "coverage_status": coverage_meta.get("status"),
        "coverage_reason": coverage_meta.get("reason"),
        "coverage_source": coverage_meta.get("source"),
        "duplication_percentage": _number_measure(measures, "duplicated_lines_density") if sonar_payload else None,
        "cognitive_complexity": _number_measure(measures, "cognitive_complexity") if sonar_payload else None,
        "reliability_rating": measures.get("reliability_rating") if sonar_payload else None,
        "maintainability_rating": measures.get("sqale_rating") if sonar_payload else None,
        "technical_debt_minutes": _number_measure(measures, "sqale_index") if sonar_payload else None,
        "lines_of_code": _number_measure(measures, "ncloc") if sonar_payload else None,
    }


def build_sonar_dashboard_payload(run: AnalysisRun, db: Session | None = None) -> dict[str, Any]:
    metric_rows = []
    if db is not None:
        metric_rows = (
            db.query(CodeMetrics)
            .filter(CodeMetrics.analysis_run_id == run.id)
            .all()
        )

    sonar_payload = get_sonar_payload(run)
    valid_files = _valid_analysis_files(metric_rows)
    sonar_file_measures = _filter_sonar_file_measures_for_analysis(
        get_sonar_file_measure_map(sonar_payload),
        valid_files,
    )
    file_metrics = _build_file_metrics(metric_rows, sonar_file_measures)
    complex_functions = _build_complex_functions(metric_rows)
    if sonar_payload is None:
        skill_score_fields = build_skill_score_fields(_first_skill_score(run))
        return {
            "repository": _repository_payload(run),
            "overall": {
                **skill_score_fields,
                "sonar_health_score": None,
                "sonar_state": "sonar_unavailable",
                "quality_gate": None,
            },
            "project_size": {
                "lines_of_code": None,
                "files": None,
                "directories": None,
                "functions": None,
                "classes": None,
                "statements": None,
            },
            "file_metrics": file_metrics,
            "complex_functions": complex_functions,
            "analysis_summary": {
                "source": "sonarqube",
                "project_key": None,
                "metrics_count": 0,
                "issues_count": 0,
            },
        }

    quality_gate = (sonar_payload.get("quality_gate") or {}).get("projectStatus") or {}
    measures = get_sonar_measure_map(sonar_payload)
    issues = get_sonar_issues(sonar_payload)
    issue_items = _filter_issues_for_analysis(
        [_issue_item(issue) for issue in issues],
        valid_files,
    )
    reliability_issues = [issue for issue in issue_items if str(issue.get("type", "")).upper() == "BUG"]
    maintainability_issues = [issue for issue in issue_items if str(issue.get("type", "")).upper() == "CODE_SMELL"]
    summary = build_sonar_repo_summary(run)
    coverage_meta = get_coverage_metadata(sonar_payload)
    coverage_available = bool(coverage_meta.get("available"))

    return {
        "repository": _repository_payload(run),
        "overall": {
            "skill_score": summary["skill_score"],
            "skill_score_level": summary["skill_score_level"],
            "sonar_health_score": summary["sonar_health_score"],
            "sonar_state": summary["sonar_state"],
            "quality_gate": quality_gate,
        },
        "reliability": {
            "rating": measures.get("reliability_rating"),
            "total_bugs": _number_measure(measures, "bugs"),
            "issues": reliability_issues,
        },
        "maintainability": {
            "rating": measures.get("sqale_rating"),
            "code_smells": _number_measure(measures, "code_smells"),
            "technical_debt_minutes": _number_measure(measures, "sqale_index"),
            "debt_ratio": _number_measure(measures, "sqale_debt_ratio"),
            "issues": maintainability_issues,
        },
        "coverage": {
            "available": coverage_available,
            "status": coverage_meta.get("status"),
            "reason": coverage_meta.get("reason"),
            "source": coverage_meta.get("source"),
            "coverage": _number_measure(measures, "coverage") if coverage_available else None,
            "line_coverage": _number_measure(measures, "line_coverage") if coverage_available else None,
            "branch_coverage": _number_measure(measures, "branch_coverage") if coverage_available else None,
            "uncovered_lines": _number_measure(measures, "uncovered_lines") if coverage_available else None,
        },
        "duplication": {
            "percentage": _number_measure(measures, "duplicated_lines_density"),
            "duplicated_lines": _number_measure(measures, "duplicated_lines"),
            "duplicated_blocks": _number_measure(measures, "duplicated_blocks"),
            "duplicated_files": _number_measure(measures, "duplicated_files"),
        },
        "complexity": {
            "cyclomatic_complexity": _number_measure(measures, "complexity"),
            "cognitive_complexity": _number_measure(measures, "cognitive_complexity"),
        },
        "project_size": {
            "lines_of_code": _number_measure(measures, "ncloc"),
            "files": _number_measure(measures, "files"),
            "directories": _number_measure(measures, "directories"),
            "functions": _number_measure(measures, "functions"),
            "classes": _number_measure(measures, "classes"),
            "statements": _number_measure(measures, "statements"),
        },
        "file_metrics": file_metrics,
        "complex_functions": complex_functions,
        "issues_explorer": issue_items,
        "analysis_summary": {
            "source": "sonarqube",
            "project_key": (run.ai_insights or {}).get("project_key") if isinstance(run.ai_insights, dict) else None,
            "metrics_count": len(measures),
            "issues_count": len(issue_items),
            **summary,
        },
    }
