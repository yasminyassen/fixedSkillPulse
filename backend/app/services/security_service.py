from __future__ import annotations

from collections import Counter
import math
import os


def normalize_severity(severity: str | None) -> str:
    value = (severity or "MEDIUM").upper()
    if value == "CRITICAL":
        return "HIGH"
    if value in {"HIGH", "MEDIUM", "LOW"}:
        return value
    return "MEDIUM"


def group_findings_by_severity_and_file(findings: list[dict]) -> dict:
    grouped: dict[str, dict[str, list[dict]]] = {
        "HIGH": {},
        "MEDIUM": {},
        "LOW": {},
    }

    for finding in findings:
        sev = normalize_severity(finding.get("severity"))
        file_path = finding.get("file_path") or "unknown"
        entry = {
            "tool": finding.get("tool"),
            "rule": finding.get("rule"),
            "owasp_category": finding.get("owasp_category") or "Unknown",
            "line_number": finding.get("line_number", 0),
            "description": finding.get("description"),
        }
        grouped[sev].setdefault(file_path, []).append(entry)

    return grouped


def _is_dependency_finding(finding: dict) -> bool:
    tool = (finding.get("tool") or "").lower()
    if tool == "safety":
        return True

    file_name = os.path.basename((finding.get("file_path") or "").replace("\\", "/")).lower()
    return file_name in {
        "requirements.txt",
        "pyproject.toml",
        "poetry.lock",
        "pipfile",
        "pipfile.lock",
    }


def _component_score(
    findings: list[dict],
    severity_weight: dict[str, float],
    cwe_weight: dict[str, float],
    total_loc: int | None = None,
    use_density: bool = False,
    saturation_scale: float = 80.0,
) -> float:
    if not findings:
        return 100.0

    raw_risk = 0.0
    for finding in findings:
        sev = normalize_severity(finding.get("severity"))
        raw_risk += severity_weight.get(sev, severity_weight["MEDIUM"]) * cwe_weight.get(finding.get("cwe"), 1.0)

    unique_files = len(set(finding.get("file_path") for finding in findings if finding.get("file_path")))
    repeated_findings = max(0, len(findings) - unique_files)

    # Convert accumulated risk into a capped, non-linear penalty. This prevents
    # medium/low repeated findings from collapsing a score to zero too quickly.
    penalty = 100.0 * (1.0 - math.exp(-raw_risk / max(saturation_scale, 1.0)))

    repetition_factor = 1.0 + min(0.18, repeated_findings * 0.01)
    spread_factor = 1.0 + min(0.18, max(0, unique_files - 1) * 0.025)
    penalty *= repetition_factor * spread_factor

    if use_density:
        findings_per_kloc = len(findings) / max((total_loc or 1) / 1000.0, 1.0)
        penalty *= min(1.25, 1.0 + findings_per_kloc * 0.025)

    return round(max(0.0, 100.0 - min(100.0, penalty)), 2)


def compute_security_score_breakdown(findings: list[dict], total_loc: int = 1000) -> dict:
    code_findings = [finding for finding in findings if not _is_dependency_finding(finding)]
    dependency_findings = [finding for finding in findings if _is_dependency_finding(finding)]

    code_score = _component_score(
        code_findings,
        severity_weight={
            "HIGH": 9,
            "MEDIUM": 4,
            "LOW": 1,
        },
        cwe_weight={
            "CWE-79": 1.5,
            "CWE-89": 1.8,
            "CWE-94": 2.2,
        },
        total_loc=total_loc,
        use_density=True,
        saturation_scale=85,
    )

    dependency_score = _component_score(
        dependency_findings,
        severity_weight={
            "HIGH": 5,
            "MEDIUM": 2.5,
            "LOW": 0.8,
        },
        cwe_weight={},
        saturation_scale=90,
    )

    overall = round((code_score * 0.6) + (dependency_score * 0.4), 2)
    return {
        "overall": overall,
        "code_security": code_score,
        "dependency_security": dependency_score,
        "weights": {
            "code_security": 0.6,
            "dependency_security": 0.4,
        },
        "finding_counts": {
            "code_security": len(code_findings),
            "dependency_security": len(dependency_findings),
        },
    }


def compute_security_score(findings: list[dict], total_loc: int = 1000) -> float:
    return compute_security_score_breakdown(findings, total_loc)["overall"]


def compute_legacy_security_score(findings: list[dict], total_loc: int = 1000) -> float:
    if not findings:
        return 100.0

    severity_weight = {
        "HIGH": 10,
        "MEDIUM": 5,
        "LOW": 2,
    }

    cwe_weight = {
        "CWE-79": 1.5,
        "CWE-89": 1.8,
        "CWE-94": 2.2,
    }

    penalty = 0.0

    for finding in findings:
        sev = normalize_severity(finding.get("severity"))
        sev_score = severity_weight.get(sev, 5)
        penalty += sev_score * cwe_weight.get(finding.get("cwe"), 1.0)

    density = len(findings) / max(total_loc, 1)
    density_factor = min(2.0, 1 + density * 50)

    unique_files = len(set(finding.get("file_path") for finding in findings))
    repetition_factor = 1 + (len(findings) - unique_files) * 0.05

    final_penalty = penalty * density_factor * repetition_factor
    return round(max(0.0, 100.0 - final_penalty), 2)
