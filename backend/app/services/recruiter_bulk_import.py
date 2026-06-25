import csv
import io
import re
from typing import Any

import pandas as pd

GITHUB_REPO_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)

HEADER_ALIASES = {
    "candidate_name": {"candidate_name", "candidate", "name", "student", "student_name", "full_name"},
    "repo_url": {
        "repo_url",
        "repository_url",
        "github_url",
        "url",
        "repo",
        "repository",
        "github_repo",
        "submission_url",
    },
    "branch": {"branch", "default_branch", "git_branch"},
}


def _normalize_header(value: str) -> str:
    return re.sub(r"[\s\-]+", "_", str(value or "").strip().lower())


def _map_headers(raw_headers: list[str]) -> dict[str, str]:
    normalized = {_normalize_header(h): h for h in raw_headers if h}
    mapping: dict[str, str] = {}
    for canonical, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[canonical] = normalized[alias]
                break
    return mapping


def _parse_repo_url(value: str) -> dict[str, str]:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Repository URL is empty")

    if not raw.startswith("http"):
        if "/" in raw:
            raw = f"https://github.com/{raw.strip('/')}"
        else:
            raise ValueError(f"Invalid repository reference: {value}")

    match = GITHUB_REPO_RE.match(raw)
    if not match:
        raise ValueError(f"Invalid GitHub repository URL: {value}")

    owner = match.group("owner")
    repo = match.group("repo")
    return {
        "repo_url": f"https://github.com/{owner}/{repo}",
        "full_name": f"{owner}/{repo}",
        "repo_name": repo,
    }


def _row_value(row: dict[str, Any], mapping: dict[str, str], key: str) -> str:
    source_key = mapping.get(key)
    if not source_key:
        return ""
    value = row.get(source_key, "")
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def parse_candidate_rows_from_dataframe(df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    if df is None or df.empty:
        raise ValueError("The uploaded file has no rows.")

    df = df.copy()
    df.columns = [str(col).strip() for col in df.columns]
    mapping = _map_headers(list(df.columns))

    if "candidate_name" not in mapping or "repo_url" not in mapping:
        found = ", ".join(str(col) for col in df.columns) if len(df.columns) else "(none)"
        raise ValueError(
            "The file structure does not match the required format. "
            "You must include a candidate name column and a repository URL column. "
            f"Found columns: {found}. "
            "Accepted examples: candidate_name + repo_url, or Candidate + GitHub URL. "
            "Optional branch column defaults to main."
        )

    rows: list[dict] = []
    skipped: list[dict] = []

    for index, raw_row in df.iterrows():
        row_number = int(index) + 2  # header row + 1-based spreadsheet row
        row_dict = {str(k): raw_row[k] for k in df.columns}
        candidate_name = _row_value(row_dict, mapping, "candidate_name")
        repo_ref = _row_value(row_dict, mapping, "repo_url")
        branch = _row_value(row_dict, mapping, "branch") or "main"

        if not candidate_name and not repo_ref:
            continue
        if not candidate_name:
            skipped.append({"row": row_number, "reason": "missing_candidate_name", "repo_url": repo_ref})
            continue
        if not repo_ref:
            skipped.append({"row": row_number, "reason": "missing_repo_url", "candidate_name": candidate_name})
            continue

        try:
            repo_meta = _parse_repo_url(repo_ref)
        except ValueError as exc:
            skipped.append({
                "row": row_number,
                "candidate_name": candidate_name,
                "repo_url": repo_ref,
                "reason": str(exc),
            })
            continue

        rows.append({
            "candidate_name": candidate_name,
            "branch": branch,
            **repo_meta,
        })

    return rows, skipped


def parse_candidate_upload(file_name: str, content: bytes) -> tuple[list[dict], list[dict]]:
    lowered = (file_name or "").lower()

    if lowered.endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise ValueError("CSV file is missing a header row.")
        rows = list(reader)
        df = pd.DataFrame(rows)
        return parse_candidate_rows_from_dataframe(df)

    if lowered.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(content))
        return parse_candidate_rows_from_dataframe(df)

    raise ValueError("Unsupported file type. Upload a .csv, .xlsx, or .xls file.")
