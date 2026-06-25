from concurrent.futures import ThreadPoolExecutor, as_completed

from app.services.security.bandit_scan import run_bandit
from app.services.security.semgrep_scan import run_semgrep
from app.services.security.safety_scan import run_safety
from app.services.security.gitleaks_scan import run_gitleaks
from app.services.security.post_processing import deduplicate_findings

#  PATCH: centralized normalization
def _normalize_finding(f: dict) -> dict:
    return {
        "tool": str(f.get("tool") or "unknown"),
        "rule": str(f.get("rule") or "unknown"),
        "file_path": (f.get("file_path") or "unknown").replace("\\", "/"),
        "severity": (f.get("severity") or "MEDIUM").upper(),
        "description": str(f.get("description") or ""),
        "line_number": int(f.get("line_number") or 0),
        "cwe": f.get("cwe") or "CWE-703",
        "owasp_category": f.get("owasp_category") or "A10",
    }
#  REASON: enforce strict schema before anything else touches the data


def run_security_analysis(repo_path):

    scanners = {
        "bandit": run_bandit,
        "semgrep": run_semgrep,
        "safety": run_safety,
        "gitleaks": run_gitleaks
    }

    findings = []
    failed_tools = []  #  PATCH
    raw_counts = {}

    with ThreadPoolExecutor(max_workers=len(scanners)) as executor:

        futures = {
            executor.submit(scanner, repo_path): name
            for name, scanner in scanners.items()
        }

        for future in as_completed(futures):

            tool_name = futures[future]

            try:
                results = future.result(timeout=400)
                raw_counts[tool_name] = len(results or [])

                if results:
                    #  PATCH: normalize here
                    normalized = [_normalize_finding(f) for f in results]
                    findings.extend(normalized)
                    print(
                        f"{tool_name} completed with {len(results)} raw findings, "
                        f"{len(normalized)} normalized findings"
                    )
                else:
                    print(f"{tool_name} completed with 0 findings")

            except Exception as e:
                print(f"{tool_name} failed:", e)
                failed_tools.append(tool_name)  #  PATCH
                raw_counts[tool_name] = None
                #  REASON: NEVER silently ignore scanner failure

    before_dedup = len(findings)
    findings = deduplicate_findings(findings)
    print(
        "security pipeline summary: "
        f"raw_counts={raw_counts}, normalized_total={before_dedup}, "
        f"deduped_total={len(findings)}, failed_tools={failed_tools}"
    )

    return {
        "findings": findings,
        "failed_tools": failed_tools  #  PATCH
    }
