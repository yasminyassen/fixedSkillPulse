from collections import defaultdict
import hashlib  #  PATCH

SEVERITY_MAP = {
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4
}


def normalize_severity(severity):
    if not severity:
        return "MEDIUM"

    s = severity.upper()

    if s in SEVERITY_MAP:
        return s

    if "ERROR" in s:
        return "HIGH"

    return "MEDIUM"


#  PATCH: stronger fingerprint
def _fingerprint(f):
    base = f"{f.get('file_path')}|{f.get('cwe')}|{(f.get('description') or '')[:80]}"
    return hashlib.sha1(base.encode()).hexdigest()
#  REASON: avoids duplicates across tools & slight variations


def deduplicate_findings(findings):

    grouped = defaultdict(list)

    for f in findings:
        key = _fingerprint(f)  #  PATCH
        grouped[key].append(f)

    deduped = []

    for group in grouped.values():

        base = next(
            (g for g in group if g.get("cwe") and g.get("cwe") != "CWE-703"),
            group[0]
        )

        tools = [g["tool"] for g in group]

        severities = [normalize_severity(g["severity"]) for g in group]
        highest = max(severities, key=lambda x: SEVERITY_MAP[x])

        base["severity"] = highest
        base["tools_detected"] = list(set(tools))

        #  PATCH: better confidence
        TOOL_TRUST = {
            "bandit": 0.9,
            "semgrep": 0.85,
            "gitleaks": 0.95,
            "safety": 0.8
        }

        score = sum(TOOL_TRUST.get(t, 0.5) for t in tools) / len(tools)

        if score > 0.85:
            base["confidence"] = "HIGH"
        elif score > 0.6:
            base["confidence"] = "MEDIUM"
        else:
            base["confidence"] = "LOW"

        #  REASON: real confidence instead of fake binary logic

        deduped.append(base)

    return deduped