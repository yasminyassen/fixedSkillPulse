import subprocess
import json
import os
import shutil
from pathlib import Path

from app.core.security_mapping import CWE_TO_OWASP
from app.core.config import settings

GITLEAKS_TO_CWE = {
    "generic-api-key": "CWE-798",
    "github-token": "CWE-522",
    "private-key": "CWE-522",
    "password": "CWE-798",
}


def _relative_path(file_path: str, repo_path: str) -> str:
    normalized = (file_path or "").replace("\\", "/")
    if not normalized or not os.path.isabs(file_path):
        return normalized or "unknown"

    try:
        rel = os.path.relpath(file_path, repo_path)
        return rel.replace("\\", "/")
    except ValueError:
        return normalized


def run_gitleaks(repo_path):
    configured = (settings.GITLEAKS_PATH or "").strip()
    exe_path = configured

    # If a directory was configured, run the binary inside it.
    configured_path = Path(configured) if configured else None
    if configured_path and configured_path.exists() and configured_path.is_dir():
        exe_path = str(configured_path / "gitleaks.exe")

    # Fallback to PATH lookup when config path is missing/invalid.
    if not exe_path or (not os.path.exists(exe_path) and not shutil.which(exe_path)):
        resolved = shutil.which("gitleaks")
        if not resolved:
            raise FileNotFoundError(
                "gitleaks executable not found. Set GITLEAKS_PATH to gitleaks.exe or install gitleaks in PATH."
            )
        exe_path = resolved

    report_path = os.path.join(repo_path, "gitleaks-report.json")
    print(f"gitleaks: using executable => {exe_path}")
    print(f"gitleaks: report path => {report_path}")

    result = subprocess.run(
        [
            exe_path,
            "detect",
            "--source",
            repo_path,
            "--no-git",
            "--report-format",
            "json",
            "--report-path",
            report_path,
            "--no-banner"
        ],
        capture_output=True,
        text=True,
        timeout=120
    )

    findings = []
    stdout = result.stdout or ""
    stderr = result.stderr or ""

    print(
        f"gitleaks: exit={result.returncode}, stdout_len={len(stdout)}, stderr_len={len(stderr)}"
    )
    if stderr.strip():
        print(f"gitleaks: stderr =>\n{stderr.strip()[:1000]}")

    if not os.path.exists(report_path):
        if result.returncode != 0:
            raise RuntimeError(f"gitleaks failed (exit={result.returncode}): {stderr[:500]}")
        print("gitleaks: no report file created and exit=0; treating as 0 findings")
        return findings

    try:
        with open(report_path, "r") as f:
            data = json.load(f)
    except Exception as exc:
        raise RuntimeError(
            f"gitleaks report was not valid JSON (exit={result.returncode}): {stderr[:500]}"
        ) from exc

    if not isinstance(data, list):
        raise RuntimeError(
            f"gitleaks report JSON had unexpected shape: {type(data).__name__}"
        )

    print(f"gitleaks: report findings count={len(data)}")
    
    for issue in data:
        rule = (issue.get("RuleID") or "").lower().replace(" ", "-")
        file_path = _relative_path(issue.get("File") or "", repo_path)

        cwe = GITLEAKS_TO_CWE.get(rule, "CWE-798")
        owasp = CWE_TO_OWASP.get(cwe, "A07")
        findings.append({
            "tool": "gitleaks",
            "rule": rule,
            "file_path": file_path,
            "severity": "HIGH",
            "description": issue.get("Description"),
            "line_number": issue.get("StartLine"),
            "cwe": cwe,
            "owasp_category": owasp
        })

    return findings
