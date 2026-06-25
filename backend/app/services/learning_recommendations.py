from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

from ai_services.rag.learning_rag import get_last_retriever, retrieve_learning_resources
from app.services.llm_client import (
    LLMError,
    _extract_json_payload,
    _max_retries,
    _ollama_config,
    _openrouter_config,
    _post_with_retry,
)

logger = logging.getLogger(__name__)

PRIORITIES = {"High", "Medium", "Low"}


def _short_text(value: object, max_len: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text[:max_len].rstrip()


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _model_dict(row: object, fields: list[str]) -> dict[str, Any]:
    return {field: getattr(row, field, None) for field in fields}


def _repo_name(run: object) -> str:
    repo = getattr(run, "repository", None)
    return (
        getattr(repo, "full_name", None)
        or getattr(repo, "name", None)
        or f"repository:{getattr(run, 'repository_id', 'unknown')}"
    )


def _normalise_resource_for_prompt(resource: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": resource.get("id"),
        "title": resource.get("title"),
        "type": resource.get("type"),
        "provider": resource.get("provider"),
        "url": resource.get("url"),
        "topics": resource.get("topics") if isinstance(resource.get("topics"), list) else [],
        "difficulty": resource.get("difficulty"),
        "estimated_effort": resource.get("estimated_effort"),
        "content": resource.get("content"),
        "score": round(_as_float(resource.get("score")), 6),
    }


def _resource_response(resource: dict[str, Any], reason: str = "") -> dict[str, str]:
    return {
        "title": _short_text(resource.get("title"), 160),
        "type": _short_text(resource.get("type"), 60),
        "provider": _short_text(resource.get("provider"), 80),
        "url": _short_text(resource.get("url"), 300),
        "reason": _short_text(reason or "Retrieved as relevant to the analysis evidence.", 180),
    }


def _sonar_issue_dict(issue: object) -> dict[str, Any]:
    if isinstance(issue, dict):
        return {
            "type": issue.get("type"),
            "severity": issue.get("severity"),
            "rule": issue.get("rule"),
            "file_path": issue.get("file_path"),
            "line": issue.get("line"),
            "message": issue.get("message"),
        }
    return _model_dict(issue, ["type", "severity", "rule", "file_path", "line", "message"])


def _security_finding_dict(finding: object) -> dict[str, Any]:
    if isinstance(finding, dict):
        return {
            "tool": finding.get("tool"),
            "rule": finding.get("rule"),
            "cwe": finding.get("cwe"),
            "file_path": finding.get("file_path"),
            "severity": finding.get("severity"),
            "description": finding.get("description"),
            "line_number": finding.get("line_number"),
            "owasp_category": finding.get("owasp_category"),
        }
    return _model_dict(
        finding,
        ["tool", "rule", "cwe", "file_path", "severity", "description", "line_number", "owasp_category"],
    )


def _metric_summary(metric_rows: list[object]) -> dict[str, Any]:
    rows = metric_rows if isinstance(metric_rows, list) else []

    def avg(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 3) if values else None

    complexity = []
    duplication = []
    maintainability = []
    loc = 0
    files = []
    for row in rows:
        raw = getattr(row, "raw_metrics", None)
        raw = raw if isinstance(raw, dict) else {}
        loc += int(getattr(row, "lines_of_code", None) or raw.get("loc") or 0)
        complexity.append(_as_float(getattr(row, "cyclomatic_complexity", None), None))  # type: ignore[arg-type]
        duplication.append(_as_float(getattr(row, "duplication_score", None), None))  # type: ignore[arg-type]
        maintainability.append(_as_float(getattr(row, "maintainability_index", None), None))  # type: ignore[arg-type]
        files.append({
            "file_path": getattr(row, "file_path", None),
            "cyclomatic_complexity": getattr(row, "cyclomatic_complexity", None),
            "duplication_score": getattr(row, "duplication_score", None),
            "maintainability_index": getattr(row, "maintainability_index", None),
            "raw_metrics": {
                key: raw.get(key)
                for key in (
                    "cognitive_complexity",
                    "test_ratio",
                    "docstring_coverage",
                    "style_violations",
                    "missing_docstrings",
                    "function_size_avg",
                )
                if key in raw
            },
        })

    return {
        "file_count": len(rows),
        "lines_of_code": loc,
        "avg_cyclomatic_complexity": avg([value for value in complexity if value is not None]),
        "avg_duplication_score": avg([value for value in duplication if value is not None]),
        "avg_maintainability_index": avg([value for value in maintainability if value is not None]),
        "highest_risk_files": sorted(
            files,
            key=lambda item: (
                _as_float(item.get("cyclomatic_complexity")),
                _as_float(item.get("duplication_score")),
            ),
            reverse=True,
        )[:10],
    }


def _extract_skill_gaps(run: object, detected_skill_gaps: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if isinstance(detected_skill_gaps, list):
        return [gap for gap in detected_skill_gaps if isinstance(gap, dict)]

    ai_insights = getattr(run, "ai_insights", None)
    if isinstance(ai_insights, dict):
        llm_skill_gaps = ai_insights.get("llm_skill_gaps")
        if isinstance(llm_skill_gaps, dict) and isinstance(llm_skill_gaps.get("skill_gaps"), list):
            return [gap for gap in llm_skill_gaps["skill_gaps"] if isinstance(gap, dict)]
    return []


def _extract_sonar_metrics(run: object, sonar_metrics: dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(sonar_metrics, dict) and sonar_metrics:
        return sonar_metrics

    summary = getattr(run, "sonar_summary", None)
    if summary is not None:
        measures = getattr(summary, "measures", None)
        measures = measures if isinstance(measures, dict) else {}
        return {
            "quality_gate": getattr(summary, "quality_gate", None),
            "sonar_health_score": getattr(summary, "sonar_health_score", None),
            **measures,
        }

    ai_insights = getattr(run, "ai_insights", None)
    if isinstance(ai_insights, dict):
        sonar = ai_insights.get("sonar")
        if isinstance(sonar, dict):
            component = (sonar.get("measures") or {}).get("component") or {}
            measures = component.get("measures") if isinstance(component, dict) else []
            if isinstance(measures, list):
                return {
                    item.get("metric"): item.get("value")
                    for item in measures
                    if isinstance(item, dict) and item.get("metric")
                }
    return {}


def _extract_sonar_issues(run: object, sonar_issues: list[object] | None) -> list[dict[str, Any]]:
    if isinstance(sonar_issues, list):
        return [_sonar_issue_dict(issue) for issue in sonar_issues]

    relationship_rows = getattr(run, "sonar_issues", None)
    if isinstance(relationship_rows, list):
        return [_sonar_issue_dict(issue) for issue in relationship_rows]
    return []


def _build_search_query(
    sonar_metrics: dict[str, Any],
    sonar_issues: list[dict[str, Any]],
    security_findings: list[dict[str, Any]],
    skill_gaps: list[dict[str, Any]],
    static_metrics: dict[str, Any],
) -> str:
    terms: list[str] = [
        "actionable developer learning recommendations",
        "SonarQube clean code practices",
    ]

    for gap in skill_gaps[:8]:
        terms.append(_short_text(gap.get("skill"), 80))
        terms.append(_short_text(gap.get("reason"), 160))
        for metric in gap.get("related_metrics") or []:
            terms.append(_short_text(metric, 80))

    coverage = _as_float(sonar_metrics.get("coverage"), -1)
    duplication = _as_float(sonar_metrics.get("duplicated_lines_density"), -1)
    cognitive = _as_float(sonar_metrics.get("cognitive_complexity"), -1)
    code_smells = _as_float(sonar_metrics.get("code_smells"), 0)
    bugs = _as_float(sonar_metrics.get("bugs"), 0)
    vulnerabilities = _as_float(sonar_metrics.get("vulnerabilities"), 0)

    if 0 <= coverage < 80:
        terms.append("Python unit testing test coverage coverage.py pytest")
    if duplication > 3 or _as_float(static_metrics.get("avg_duplication_score")) > 3:
        terms.append("duplication reduction refactoring clean code")
    if cognitive > 15 or _as_float(static_metrics.get("avg_cyclomatic_complexity")) > 10:
        terms.append("cognitive complexity code refactoring maintainability")
    if code_smells > 0:
        terms.append("clean code maintainability SonarQube code smells")
    if bugs > 0:
        terms.append("unit testing reliability regression tests")
    if vulnerabilities > 0 or security_findings:
        terms.append("secure coding OWASP Top 10 input validation secrets management SQL injection prevention")

    for issue in sonar_issues[:20]:
        terms.extend([
            _short_text(issue.get("type"), 40),
            _short_text(issue.get("severity"), 40),
            _short_text(issue.get("rule"), 80),
            _short_text(issue.get("message"), 180),
        ])

    for finding in security_findings[:20]:
        terms.extend([
            _short_text(finding.get("severity"), 40),
            _short_text(finding.get("cwe"), 40),
            _short_text(finding.get("owasp_category"), 80),
            _short_text(finding.get("description"), 180),
        ])

    return " ".join(term for term in terms if term).strip()


def _call_learning_recommendations_once(payload: dict[str, Any], ai_mode: str) -> dict[str, Any]:
    if ai_mode == "ollama":
        url, model = _ollama_config()
        body = {
            "model": model,
            "task": "learning_recommendations",
            "payload": payload,
            "response_format": "json",
            "instructions": (
                "Return only valid JSON with key recommendations. Use only resources from payload.retrieved_resources. "
                "Do not invent URLs."
            ),
        }
        jr = _post_with_retry(f"{url.rstrip('/')}/llm", body, max_retries=2)
        return jr if isinstance(jr, dict) else {}

    url, key, model = _openrouter_config()
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return only strict JSON. No markdown. Do not invent resource URLs. "
                    "Recommended resources must come only from the provided retrieved_resources list."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Generate actionable developer learning recommendations from the provided analysis evidence.\n\n"
                    "Use this exact JSON shape:\n"
                    "{\n"
                    "  \"recommendations\": [\n"
                    "    {\n"
                    "      \"skill\": \"string\",\n"
                    "      \"why_needed\": \"string\",\n"
                    "      \"priority\": \"High|Medium|Low\",\n"
                    "      \"learning_objectives\": [\"string\"],\n"
                    "      \"estimated_effort\": \"string\",\n"
                    "      \"expected_improvement\": \"string\",\n"
                    "      \"resources\": [\n"
                    "        {\"id\": \"resource id from retrieved_resources\", \"reason\": \"why this resource fits\"}\n"
                    "      ]\n"
                    "    }\n"
                    "  ]\n"
                    "}\n\n"
                    "Rules:\n"
                    "- Base recommendations on sonar_metrics, sonar_issues, security_findings, detected_skill_gaps, and retrieved_resources.\n"
                    "- Do not include dashboard summary metrics or skill gap cards.\n"
                    "- Do not invent resource IDs, titles, providers, or URLs.\n"
                    "- If retrieved_resources is empty, still produce recommendations but use empty resources arrays.\n"
                    "- Prefer 2 to 5 recommendations.\n\n"
                    f"Input:\n{json.dumps(payload, ensure_ascii=False)}"
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 3000,
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    jr = _post_with_retry(f"{url.rstrip('/')}/chat/completions", body, headers=headers, max_retries=2)
    return _extract_json_payload((jr.get("choices") or [{}])[0].get("message", {}).get("content", "")) if isinstance(jr, dict) else {}


def _normalise_recommendations(resp: dict[str, Any], retrieved_resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(resp, dict) or not isinstance(resp.get("recommendations"), list):
        return []

    by_id = {str(resource.get("id")): resource for resource in retrieved_resources if resource.get("id")}
    by_url = {str(resource.get("url")): resource for resource in retrieved_resources if resource.get("url")}
    recommendations: list[dict[str, Any]] = []

    for item in resp["recommendations"]:
        if not isinstance(item, dict):
            continue
        skill = _short_text(item.get("skill"), 100)
        why_needed = _short_text(item.get("why_needed"), 300)
        if not skill or not why_needed:
            continue

        objectives = item.get("learning_objectives")
        if not isinstance(objectives, list):
            objectives = []
        objectives = [_short_text(objective, 180) for objective in objectives if _short_text(objective, 180)][:5]

        resources = []
        for raw_resource in item.get("resources") or []:
            if not isinstance(raw_resource, dict):
                continue
            resource = by_id.get(str(raw_resource.get("id"))) or by_url.get(str(raw_resource.get("url")))
            if not resource:
                continue
            resources.append(_resource_response(resource, str(raw_resource.get("reason") or "")))

        priority = str(item.get("priority") or "").strip().title()
        recommendations.append({
            "skill": skill,
            "why_needed": why_needed,
            "priority": priority if priority in PRIORITIES else "Medium",
            "learning_objectives": objectives or [f"Apply {skill} practices to the highest-risk findings in this analysis."],
            "estimated_effort": _short_text(item.get("estimated_effort"), 80) or "2-4 hours",
            "expected_improvement": _short_text(item.get("expected_improvement"), 240) or "Reduce recurring findings and improve code review readiness.",
            "resources": resources[:3],
        })

    return recommendations[:5]


def _fallback_recommendations(
    retrieved_resources: list[dict[str, Any]],
    skill_gaps: list[dict[str, Any]],
    sonar_metrics: dict[str, Any],
    security_findings: list[dict[str, Any]],
    sonar_issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    resource_pool = retrieved_resources[:5]

    def matching_resources(skill: str) -> list[dict[str, str]]:
        skill_tokens = set(re.findall(r"[a-z0-9]+", skill.lower()))
        matched = []
        for resource in resource_pool:
            topics = " ".join(resource.get("topics") or [])
            haystack = f"{resource.get('title')} {topics} {resource.get('content')}".lower()
            if not skill_tokens or any(token in haystack for token in skill_tokens):
                matched.append(_resource_response(resource, f"Retrieved for {skill} based on the analysis evidence."))
        return (matched or [_resource_response(resource, "Retrieved as one of the most relevant resources.") for resource in resource_pool])[:3]

    recommendations: list[dict[str, Any]] = []
    for gap in skill_gaps[:4]:
        skill = _short_text(gap.get("skill"), 100) or "Clean Code"
        recommendations.append({
            "skill": skill,
            "why_needed": _short_text(gap.get("reason"), 260) or "Detected skill gap evidence indicates this topic needs focused practice.",
            "priority": str(gap.get("priority") or "Medium").title() if str(gap.get("priority") or "").title() in PRIORITIES else "Medium",
            "learning_objectives": [
                f"Explain the main practices behind {skill}.",
                "Apply the practices to the highest-risk files or findings from this analysis.",
                "Add review checks that prevent the same issue pattern from recurring.",
            ],
            "estimated_effort": resource_pool[0].get("estimated_effort") if resource_pool else "2-4 hours",
            "expected_improvement": "Reduce repeated findings and improve maintainability, reliability, or security signals in the next analysis.",
            "resources": matching_resources(skill),
        })

    if recommendations:
        return recommendations[:5]

    if security_findings or _as_float(sonar_metrics.get("vulnerabilities")) > 0:
        recommendations.append({
            "skill": "Secure Coding",
            "why_needed": "Security findings or vulnerability signals indicate a need to strengthen secure implementation habits.",
            "priority": "High",
            "learning_objectives": [
                "Map findings to OWASP risk categories.",
                "Fix validation, injection, secrets, and configuration issues using repeatable secure coding checks.",
            ],
            "estimated_effort": resource_pool[0].get("estimated_effort") if resource_pool else "3-5 hours",
            "expected_improvement": "Fewer high-risk security findings and stronger prevention of recurring vulnerability patterns.",
            "resources": matching_resources("secure coding OWASP input validation secrets SQL injection"),
        })

    coverage = _as_float(sonar_metrics.get("coverage"), -1)
    if coverage < 80 or any(str(issue.get("type")).upper() == "BUG" for issue in sonar_issues):
        recommendations.append({
            "skill": "Python Unit Testing",
            "why_needed": "Coverage, bug, or reliability signals show that more regression-focused tests would reduce change risk.",
            "priority": "High" if coverage >= 0 and coverage < 60 else "Medium",
            "learning_objectives": [
                "Write focused unit tests for boundary cases and bug-prone paths.",
                "Use coverage reports to find meaningful untested behavior.",
            ],
            "estimated_effort": resource_pool[0].get("estimated_effort") if resource_pool else "2-4 hours",
            "expected_improvement": "Higher coverage and fewer regressions around changed code.",
            "resources": matching_resources("Python unit testing coverage pytest unittest"),
        })

    if not recommendations:
        recommendations.append({
            "skill": "Clean Code and Maintainability",
            "why_needed": "Sonar and static analysis evidence should be converted into concrete refactoring practice.",
            "priority": "Medium",
            "learning_objectives": [
                "Prioritize code smells by risk and locality.",
                "Refactor complex or duplicated code in small reviewed steps.",
            ],
            "estimated_effort": resource_pool[0].get("estimated_effort") if resource_pool else "2-4 hours",
            "expected_improvement": "Improved maintainability and easier future reviews.",
            "resources": matching_resources("clean code maintainability refactoring duplication cognitive complexity"),
        })

    return recommendations[:5]


def _has_analysis_evidence(
    sonar_metrics: dict[str, Any],
    sonar_issues: list[dict[str, Any]],
    security_findings: list[dict[str, Any]],
    skill_gaps: list[dict[str, Any]],
    static_metrics: dict[str, Any],
) -> bool:
    if sonar_issues or security_findings or skill_gaps:
        return True
    if int(static_metrics.get("file_count") or 0) > 0 or int(static_metrics.get("lines_of_code") or 0) > 0:
        return True
    if sonar_metrics.get("sonar_summary_available") is True:
        return True
    if isinstance(sonar_metrics.get("sonar_file_metrics"), list) and sonar_metrics.get("sonar_file_metrics"):
        return True
    metric_keys = (
        "coverage",
        "bugs",
        "code_smells",
        "vulnerabilities",
        "duplicated_lines_density",
        "cognitive_complexity",
        "sonar_health_score",
        "quality_gate",
    )
    return any(sonar_metrics.get(key) not in (None, "", []) for key in metric_keys)


def build_learning_recommendations(
    run: object,
    score_row: object,
    metric_rows: list[object],
    security_findings: list[object],
    sonar_metrics: dict[str, Any] | None = None,
    sonar_issues: list[object] | None = None,
    detected_skill_gaps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    sonar_metrics_payload = _extract_sonar_metrics(run, sonar_metrics)
    sonar_issue_payload = _extract_sonar_issues(run, sonar_issues)[:50]
    security_payload = [_security_finding_dict(finding) for finding in (security_findings or [])][:50]
    skill_gap_payload = _extract_skill_gaps(run, detected_skill_gaps)[:20]
    static_metrics = _metric_summary(metric_rows or [])

    if not _has_analysis_evidence(
        sonar_metrics=sonar_metrics_payload,
        sonar_issues=sonar_issue_payload,
        security_findings=security_payload,
        skill_gaps=skill_gap_payload,
        static_metrics=static_metrics,
    ):
        return {
            "analysis_run_id": int(getattr(run, "id", 0) or 0),
            "repo": _repo_name(run),
            "branch": getattr(run, "branch", None) or "main",
            "recommendations": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "rag_metadata": {
                "enabled": False,
                "retrieved_count": 0,
                "retriever": "keyword_fallback",
            },
        }

    query = _build_search_query(
        sonar_metrics=sonar_metrics_payload,
        sonar_issues=sonar_issue_payload,
        security_findings=security_payload,
        skill_gaps=skill_gap_payload,
        static_metrics=static_metrics,
    )
    retrieved = retrieve_learning_resources(query, top_k=7)
    retriever = get_last_retriever()
    rag_enabled = retriever == "faiss"

    prompt_payload = {
        "repo": _repo_name(run),
        "branch": getattr(run, "branch", None) or "main",
        "score_context": {
            "code_quality_score": getattr(score_row, "code_quality_score", None),
            "maintainability_score": getattr(score_row, "maintainability_score", None),
            "security_awareness_score": getattr(score_row, "security_awareness_score", None),
            "overall_score": getattr(score_row, "overall_score", None),
        },
        "sonar_metrics": sonar_metrics_payload,
        "sonar_issues": sonar_issue_payload,
        "security_findings": security_payload,
        "detected_skill_gaps": skill_gap_payload,
        "static_metrics": static_metrics,
        "retrieved_resources": [_normalise_resource_for_prompt(resource) for resource in retrieved],
    }

    recommendations: list[dict[str, Any]] = []
    ai_mode = (os.environ.get("AI_MODE") or "openrouter").lower()
    for attempt in range(1, _max_retries() + 1):
        try:
            llm_resp = _call_learning_recommendations_once(prompt_payload, ai_mode)
            recommendations = _normalise_recommendations(llm_resp, retrieved)
        except Exception as exc:
            logger.warning("learning_recommendations attempt %d failed: %s", attempt, exc)
            recommendations = []

        if recommendations:
            break
        if attempt < _max_retries():
            time.sleep(2 ** (attempt - 1))

    if not recommendations:
        recommendations = _fallback_recommendations(
            retrieved_resources=retrieved,
            skill_gaps=skill_gap_payload,
            sonar_metrics=sonar_metrics_payload,
            security_findings=security_payload,
            sonar_issues=sonar_issue_payload,
        )

    return {
        "analysis_run_id": int(getattr(run, "id", 0) or 0),
        "repo": _repo_name(run),
        "branch": getattr(run, "branch", None) or "main",
        "recommendations": recommendations,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rag_metadata": {
            "enabled": bool(rag_enabled),
            "retrieved_count": len(retrieved),
            "retriever": retriever if retriever in {"faiss", "keyword_fallback"} else "keyword_fallback",
        },
    }
