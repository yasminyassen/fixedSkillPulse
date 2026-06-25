from __future__ import annotations

import os
import sys
import shutil
import re
import subprocess
import time
import xml.etree.ElementTree as ET
import logging
from pathlib import Path
from typing import Any

import httpx


logger = logging.getLogger(__name__)

SONAR_HOST_URL = os.environ.get("SONAR_HOST_URL", "http://localhost:9000").rstrip("/")
SONAR_SCANNER_PATH = os.environ.get("SONAR_SCANNER_PATH", "").strip()
SONAR_SCANNER_TIMEOUT = int(os.environ.get("SONAR_SCANNER_TIMEOUT", "600"))
SONAR_CE_TIMEOUT = int(os.environ.get("SONAR_CE_TIMEOUT", "180"))
SONAR_PYTEST_TIMEOUT = int(os.environ.get("SONAR_PYTEST_TIMEOUT", "300"))
SONAR_RUN_TEST_COVERAGE = os.environ.get("SONAR_RUN_TEST_COVERAGE", "1").lower() not in {"0", "false", "no"}
SONAR_METRICS = [
    "bugs",
    "reliability_rating",
    "code_smells",
    "sqale_rating",
    "sqale_index",
    "sqale_debt_ratio",
    "coverage",
    "line_coverage",
    "branch_coverage",
    "uncovered_lines",
    "duplicated_lines_density",
    "duplicated_lines",
    "duplicated_blocks",
    "duplicated_files",
    "complexity",
    "cognitive_complexity",
    "ncloc",
    "files",
    "directories",
    "functions",
    "classes",
    "statements",
]
SONAR_ISSUE_TYPES = ["BUG", "CODE_SMELL"]
SONAR_FILE_METRICS = [
    "coverage",
    "duplicated_lines",
    "duplicated_lines_density",
    "ncloc",
    "complexity",
    "cognitive_complexity",
    "functions",
    "classes",
    "statements",
]


def _safe_project_key(value: str) -> str:
    key = re.sub(r"[^A-Za-z0-9_.:-]+", "_", value).strip("_")
    return key or "skill_pulse_repository"


def _auth() -> tuple[str, str] | None:
    token = os.environ.get("SONAR_TOKEN")
    if not token:
        return None
    return token, ""


def _existing_test_paths(repo_path: str) -> list[str]:
    root = Path(repo_path)
    candidates = ["tests", "test", "src/tests"]
    return [candidate for candidate in candidates if (root / candidate).exists()]


def normalize_included_files(included_files: list[str] | None) -> list[str]:
    if not included_files:
        return []
    normalized_files = {
        str(path or "").replace("\\", "/").strip().lstrip("/")
        for path in included_files
    }
    return sorted(
        path
        for path in normalized_files
        if path and path.endswith(".py")
    )


def _has_python_tests(repo_path: str) -> bool:
    root = Path(repo_path)
    for pattern in ("test_*.py", "*_test.py"):
        if any(root.rglob(pattern)):
            return True
    return False


def _candidate_coverage_reports(repo_path: str) -> list[Path]:
    """Find coverage XML reports that already exist in the checked-out repo."""
    root = Path(repo_path)
    candidates: list[Path] = []
    for pattern in ("coverage.xml", "**/coverage.xml", "**/coverage-*.xml", "**/cobertura.xml"):
        for path in root.glob(pattern):
            if path.is_file() and ".git" not in path.parts and ".scannerwork" not in path.parts:
                candidates.append(path)

    # Keep deterministic order and remove duplicates. Prefer repo-root coverage.xml.
    unique = []
    seen = set()
    for path in sorted(candidates, key=lambda p: (0 if p == root / "coverage.xml" else 1, len(p.parts), str(p))):
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def prepare_coverage_report(repo_path: str, uploaded_coverage_path: str | None = None) -> dict[str, Any]:
    """Prepare a coverage XML report for SonarQube without executing project tests.

    Priority:
    1. A developer-uploaded coverage XML file.
    2. An existing coverage XML file committed in the repository.
    3. Unavailable, with a clear reason for the UI.

    SonarQube imports coverage reports but does not run tests itself. SkillPulse
    intentionally avoids installing dependencies or executing arbitrary project
    tests in this flow.
    """
    root = Path(repo_path)
    target_path = root / "coverage.xml"
    result: dict[str, Any] = {
        "enabled": True,
        "source": None,
        "status": "unavailable",
        "reason": "coverage_report_not_found",
        "coverage_path": str(target_path),
        "coverage_file_exists": False,
        "uploaded_coverage_path": uploaded_coverage_path,
        "repo_coverage_candidates": [],
    }

    def _looks_like_xml(path: Path) -> bool:
        try:
            head = path.read_text(encoding="utf-8", errors="ignore")[:500].lstrip()
        except OSError:
            return False
        return head.startswith("<?xml") or "<coverage" in head or "<report" in head

    if uploaded_coverage_path:
        uploaded = Path(uploaded_coverage_path)
        if uploaded.exists() and uploaded.is_file() and _looks_like_xml(uploaded):
            if uploaded.resolve() != target_path.resolve():
                shutil.copyfile(uploaded, target_path)
            result.update({
                "source": "uploaded",
                "status": "ready",
                "reason": None,
                "coverage_file_exists": target_path.exists(),
                "coverage_path": str(target_path),
            })
            return result
        result.update({
            "source": "uploaded",
            "status": "invalid",
            "reason": "uploaded_coverage_xml_missing_or_invalid",
            "coverage_file_exists": False,
        })
        return result

    candidates = _candidate_coverage_reports(repo_path)
    result["repo_coverage_candidates"] = [str(path.relative_to(root)) for path in candidates]
    if candidates:
        selected = candidates[0]
        if selected.resolve() != target_path.resolve():
            shutil.copyfile(selected, target_path)
        result.update({
            "source": "repository",
            "status": "ready",
            "reason": None,
            "coverage_file_exists": target_path.exists(),
            "coverage_path": str(target_path),
            "selected_repo_coverage_path": str(selected.relative_to(root)),
        })
        return result

    return result


def _is_excluded_python_path(path: Path) -> bool:
    excluded_parts = {".git", ".scannerwork", "__pycache__", "site-packages", "venv", ".venv"}
    return any(part in excluded_parts for part in path.parts)


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def normalize_coverage_xml_paths(coverage_path: str, repo_path: str) -> dict[str, Any]:
    repo = Path(repo_path).resolve()
    xml_path = Path(coverage_path).resolve()

    try:
        tree = ET.parse(xml_path)
    except ET.ParseError as exc:
        return {
            "matched_files": 0,
            "unmatched_files": [],
            "ambiguous_files": [],
            "error": f"invalid_coverage_xml: {exc}",
        }

    root = tree.getroot()
    repo_python_files = [
        path
        for path in repo.rglob("*.py")
        if path.is_file() and not _is_excluded_python_path(path)
    ]

    by_relative_path = {
        path.relative_to(repo).as_posix(): path.relative_to(repo).as_posix()
        for path in repo_python_files
    }
    relative_paths = list(by_relative_path)

    by_filename: dict[str, str] = {}
    duplicate_filenames: set[str] = set()
    for path in repo_python_files:
        name = path.name
        relative = path.relative_to(repo).as_posix()
        if name in by_filename:
            duplicate_filenames.add(name)
        else:
            by_filename[name] = relative

    matched = 0
    unmatched: list[str] = []
    ambiguous: list[str] = []

    for class_node in (node for node in root.iter() if _xml_local_name(node.tag) == "class"):
        original_filename = class_node.get("filename")
        if not original_filename:
            continue

        normalized = original_filename.replace("\\", "/").lstrip("/")
        if normalized in by_relative_path:
            class_node.set("filename", by_relative_path[normalized])
            matched += 1
            continue

        suffix_matches = [
            relative
            for relative in relative_paths
            if normalized.endswith(f"/{relative}")
        ]
        if len(suffix_matches) == 1:
            class_node.set("filename", suffix_matches[0])
            matched += 1
            continue
        if len(suffix_matches) > 1:
            ambiguous.append(original_filename)
            continue

        basename = Path(normalized).name
        if basename in duplicate_filenames:
            ambiguous.append(original_filename)
            continue

        if basename in by_filename:
            class_node.set("filename", by_filename[basename])
            matched += 1
        else:
            unmatched.append(original_filename)

    sources = next((node for node in root.iter() if _xml_local_name(node.tag) == "sources"), None)
    if sources is None:
        sources = ET.SubElement(root, "sources")
    for child in list(sources):
        sources.remove(child)
    source = ET.SubElement(sources, "source")
    source.text = str(repo)

    tree.write(xml_path, encoding="utf-8", xml_declaration=True)

    return {
        "matched_files": matched,
        "unmatched_files": unmatched,
        "ambiguous_files": ambiguous,
    }


def write_sonar_properties(
    repo_path: str,
    project_key: str,
    project_name: str | None = None,
    host_url: str = SONAR_HOST_URL,
    coverage_report_path: str | None = None,
    included_files: list[str] | None = None,
) -> str:
    properties_path = Path(repo_path) / "sonar-project.properties"
    test_paths = _existing_test_paths(repo_path)
    exclusions = [
        "**/.git/**",
        "**/.scannerwork/**",
        "**/node_modules/**",
        "**/.venv/**",
        "**/venv/**",
        "**/__pycache__/**",
        "**/site-packages/**",
    ]
    properties = {
        "sonar.projectKey": _safe_project_key(project_key),
        "sonar.projectName": project_name or project_key,
        "sonar.sources": ".",
        "sonar.host.url": host_url,
        "sonar.sourceEncoding": "UTF-8",
        "sonar.exclusions": ",".join(exclusions),
    }
    if test_paths:
        properties["sonar.tests"] = ",".join(test_paths)
        properties["sonar.test.inclusions"] = "**/test_*.py,**/*_test.py"
    normalized_inclusions = normalize_included_files(included_files)
    if normalized_inclusions:
        properties["sonar.inclusions"] = ",".join(normalized_inclusions)
    if coverage_report_path and Path(coverage_report_path).exists():
        properties["sonar.python.coverage.reportPaths"] = str(Path(coverage_report_path).name)
    if os.environ.get("SONAR_TOKEN"):
        properties["sonar.token"] = os.environ["SONAR_TOKEN"]

    content = "\n".join(f"{key}={value}" for key, value in properties.items()) + "\n"
    properties_path.write_text(content, encoding="utf-8")
    return str(properties_path)


def _scanner_command() -> list[str]:
    """
    Resolve the SonarScanner executable.

    On Windows, SonarScanner is commonly a .bat file. Calling just
    "sonar-scanner" from subprocess can fail with WinError 2 in services
    launched before PATH was refreshed, so SONAR_SCANNER_PATH allows using
    the absolute .bat path directly.
    """
    scanner = SONAR_SCANNER_PATH or shutil.which("sonar-scanner") or "sonar-scanner"

    if os.name == "nt" and scanner.lower().endswith((".bat", ".cmd")):
        return ["cmd", "/c", scanner]

    return [scanner]


def run_sonar_scanner(repo_path: str, timeout: int | None = None) -> dict[str, Any]:
    command = _scanner_command()
    completed = subprocess.run(
        command,
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=timeout or SONAR_SCANNER_TIMEOUT,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "sonar-scanner failed using command "
            + repr(command)
            + ": "
            + (completed.stderr.strip() or completed.stdout.strip() or f"exit code {completed.returncode}")
        )

    report_path = Path(repo_path) / ".scannerwork" / "report-task.txt"
    report: dict[str, str] = {}
    if report_path.exists():
        for line in report_path.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                report[key.strip()] = value.strip()

    return {
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "report_task": report,
    }


def _get_json(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    with httpx.Client(base_url=SONAR_HOST_URL, timeout=30.0, auth=_auth()) as client:
        response = client.get(path, params=params)
        response.raise_for_status()
        return response.json()


def _wait_for_completion(scanner_result: dict[str, Any], timeout: int = SONAR_CE_TIMEOUT) -> dict[str, Any]:
    task_id = (scanner_result.get("report_task") or {}).get("ceTaskId")
    if not task_id:
        return {}

    deadline = time.time() + timeout
    while time.time() < deadline:
        task = _get_json("/api/ce/task", {"id": task_id})
        status = ((task.get("task") or {}).get("status") or "").upper()
        if status in {"SUCCESS", "FAILED", "CANCELED"}:
            return task
        time.sleep(2)

    raise TimeoutError("Timed out waiting for SonarQube background task completion")


def get_quality_gate(project_key: str) -> dict[str, Any]:
    return _get_json("/api/qualitygates/project_status", {"projectKey": _safe_project_key(project_key)})


def get_measures(project_key: str) -> dict[str, Any]:
    """Fetch SonarQube measures safely.

    Some SonarQube versions remove/rename metrics. When that happens,
    /api/measures/component can fail the whole request. We first ask
    SonarQube which metrics exist, then request only the supported ones.
    """
    project_key = _safe_project_key(project_key)
    metrics = get_supported_metrics(SONAR_METRICS)
    if not metrics:
        return {"component": {"key": project_key, "measures": []}}

    return _get_json(
        "/api/measures/component",
        {
            "component": project_key,
            "metricKeys": ",".join(metrics),
        },
    )


def _component_is_file(component: dict[str, Any]) -> bool:
    qualifier = str(component.get("qualifier") or "").upper()
    if qualifier == "FIL":
        return True

    if qualifier and qualifier not in {"FIL", "UTS"}:
        return False

    candidate = str(
        component.get("path")
        or component.get("name")
        or component.get("key")
        or ""
    ).replace("\\", "/")
    return bool(Path(candidate).suffix)


def get_file_measures(project_key: str) -> dict[str, Any]:
    project_key = _safe_project_key(project_key)
    metric_keys = get_supported_metrics(SONAR_FILE_METRICS)
    if not metric_keys:
        return {"components": []}

    params = {
        "component": project_key,
        "metricKeys": ",".join(metric_keys),
        "qualifiers": "FIL",
        "ps": 500,
    }
    payload = _get_json(
        "/api/measures/component_tree",
        params,
    )
    if payload.get("components"):
        return payload

    fallback_params = dict(params)
    fallback_params.pop("qualifiers", None)
    fallback = _get_json("/api/measures/component_tree", fallback_params)
    fallback["components"] = [
        component
        for component in fallback.get("components", [])
        if isinstance(component, dict) and _component_is_file(component)
    ]
    return fallback


def safe_get_file_measures(project_key: str) -> dict[str, Any]:
    try:
        return get_file_measures(project_key)
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response else None
        logger.warning(
            "SonarQube file-level measures unavailable project_key=%s status_code=%s error=%s",
            project_key,
            status_code,
            exc,
        )
        return {
            "components": [],
            "paging": {"pageIndex": 1, "pageSize": 500, "total": 0},
            "unavailable": True,
            "reason": (
                "sonarqube_file_measures_forbidden"
                if status_code == 403
                else "sonarqube_file_measures_unavailable"
            ),
            "status_code": status_code,
            "error": str(exc),
        }
    except Exception as exc:
        logger.warning(
            "SonarQube file-level measures unavailable project_key=%s error=%s",
            project_key,
            exc,
            exc_info=True,
        )
        return {
            "components": [],
            "paging": {"pageIndex": 1, "pageSize": 500, "total": 0},
            "unavailable": True,
            "reason": "sonarqube_file_measures_unavailable",
            "error": str(exc),
        }


def get_supported_metrics(metric_keys: list[str]) -> list[str]:
    """Return only metric keys available on the running SonarQube instance."""
    try:
        payload = _get_json(
            "/api/metrics/search",
            {
                "ps": 500,
            },
        )
    except httpx.HTTPError:
        # If the metrics endpoint is unavailable for any reason, fall back to
        # the conservative list already defined in SONAR_METRICS.
        return metric_keys

    supported = {
        metric.get("key")
        for metric in payload.get("metrics", [])
        if isinstance(metric, dict) and metric.get("key")
    }
    if not supported:
        return metric_keys

    return [metric for metric in metric_keys if metric in supported]


def get_issues(project_key: str, page_size: int = 500) -> dict[str, Any]:
    project_key = _safe_project_key(project_key)
    issues: list[dict[str, Any]] = []
    page = 1
    paging: dict[str, Any] = {}

    while True:
        payload = _get_json(
            "/api/issues/search",
            {
                "componentKeys": project_key,
                "types": ",".join(SONAR_ISSUE_TYPES),
                "ps": page_size,
                "p": page,
            },
        )
        raw_issues = payload.get("issues") or []
        issues.extend(
            issue
            for issue in raw_issues
            if str(issue.get("type", "")).upper() in SONAR_ISSUE_TYPES
        )
        paging = payload.get("paging") or {}
        total = int(paging.get("total") or len(issues))
        if page * page_size >= total or not raw_issues:
            break
        page += 1

    return {"issues": issues, "paging": paging}


def run_sonar_analysis(
    repo_path: str,
    full_name: str,
    branch: str,
    coverage_report_path: str | None = None,
    included_files: list[str] | None = None,
) -> dict[str, Any]:
    project_key = _safe_project_key(f"skill-pulse:{full_name}:{branch}")
    coverage = prepare_coverage_report(repo_path, uploaded_coverage_path=coverage_report_path)
    if coverage.get("coverage_file_exists"):
        normalization_result = normalize_coverage_xml_paths(
            coverage["coverage_path"],
            repo_path,
        )
        coverage["path_normalization"] = normalization_result
        if normalization_result.get("error"):
            coverage.update({
                "status": "invalid",
                "reason": "coverage_xml_could_not_be_parsed",
            })
        elif normalization_result["matched_files"] == 0:
            coverage.update({
                "status": "invalid",
                "reason": "coverage_paths_do_not_match_repository",
            })

    coverage_report_for_sonar = (
        coverage.get("coverage_path")
        if coverage.get("coverage_file_exists") and coverage.get("status") != "invalid"
        else None
    )
    write_sonar_properties(
        repo_path=repo_path,
        project_key=project_key,
        project_name=f"{full_name} ({branch})",
        coverage_report_path=coverage_report_for_sonar,
        included_files=included_files,
    )
    scanner = run_sonar_scanner(repo_path)
    ce_task = _wait_for_completion(scanner)
    return {
        "source": "sonarqube",
        "project_key": project_key,
        "sonar": {
            "coverage": coverage,
            "scanner": scanner,
            "ce_task": ce_task,
            "quality_gate": get_quality_gate(project_key),
            "measures": get_measures(project_key),
            "file_measures": safe_get_file_measures(project_key),
            "issues": get_issues(project_key),
        },
    }
