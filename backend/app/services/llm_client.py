import os
import json
import re
import httpx
import logging
import time
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _get_env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _openrouter_config():
    url = _get_env("OPENROUTER_API_URL", "OPENROUTER_API", "openrouter_api_url") or "https://api.openrouter.ai/v1"
    key = _get_env("OPENROUTER_API_KEY", "openrouter_api_key", "OPENROUTER_KEY")
    model = _get_env("OPENROUTER_MODEL", "openrouter_model")
    if not key or not model:
        raise LLMError("OPENROUTER_API_KEY and OPENROUTER_MODEL must be set to use OpenRouter")
    return url, key, model


def _ollama_config():
    url = _get_env("OLLAMA_BASE_URL", "ollama_base_url")
    model = _get_env("OLLAMA_MODEL", "ollama_model")
    if not url or not model:
        raise LLMError("OLLAMA_BASE_URL and OLLAMA_MODEL must be set to use Ollama")
    return url, model


def _llm_timeout() -> httpx.Timeout:
    raw = _get_env("LLM_TIMEOUT_SECONDS", "llm_timeout_seconds")
    try:
        seconds = float(raw) if raw else 60.0
    except ValueError:
        seconds = 60.0
    return httpx.Timeout(max(5.0, min(300.0, seconds)))


def _max_retries() -> int:
    raw = _get_env("LLM_MAX_RETRIES", "llm_max_retries")
    if raw:
        try:
            return max(1, min(5, int(raw)))
        except ValueError:
            pass
    try:
        from app.core.config import settings
        return max(1, min(5, int(settings.llm_max_retries)))
    except Exception:
        return 3


def _model_context_limit() -> int:
    """Token limit for the model. Set LLM_CONTEXT_LIMIT in env to match your model."""
    raw = _get_env("LLM_CONTEXT_LIMIT", "llm_context_limit")
    try:
        return max(4_000, int(raw)) if raw else 26_000
    except ValueError:
        return 26_000


# Rough chars-per-token ratio for code/JSON (conservative)
_CHARS_PER_TOKEN = 3
# Tokens reserved for system prompt + instruction text + JSON response
_PROMPT_OVERHEAD_TOKENS = 4_000


def _payload_char_budget() -> int:
    """Total chars we can spend on file content (across all files in one call)."""
    available_tokens = _model_context_limit() - _PROMPT_OVERHEAD_TOKENS
    return max(2_000, available_tokens * _CHARS_PER_TOKEN)


# ---------------------------------------------------------------------------
# File prioritization and smart payload building
# ---------------------------------------------------------------------------

# Extensions that are pure boilerplate / not worth full content
_LOW_VALUE_EXTENSIONS = {
    ".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml", ".cfg",
    ".ini", ".env", ".lock", ".sum", ".mod", ".gitignore", ".dockerignore",
    ".csv", ".xml", ".html", ".css", ".scss", ".svg", ".png", ".jpg",
    ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".eot",
}

# Path fragments that strongly indicate generated/vendor/boilerplate
_LOW_VALUE_PATH_FRAGMENTS = (
    "node_modules/", "vendor/", ".git/", "dist/", "build/", "__pycache__/",
    "migrations/", "static/", "assets/", "fixtures/", "generated/",
    "setup.py", "setup.cfg", "conftest.py", "manage.py", "wsgi.py", "asgi.py",
    "requirements", "package.json", "package-lock", "yarn.lock",
)


def _file_priority_score(path: str, content: str) -> int:
    """
    Higher score = more important to include with full content.
    Combines file type, path signals, and content complexity signals.
    """
    path_lower = (path or "").lower()
    ext = "." + path_lower.rsplit(".", 1)[-1] if "." in path_lower else ""

    # Immediate deprioritize: boilerplate extensions
    if ext in _LOW_VALUE_EXTENSIONS:
        return 0

    # Deprioritize by path patterns
    if any(frag in path_lower for frag in _LOW_VALUE_PATH_FRAGMENTS):
        return 5

    score = 50  # base

    # Boost for main source extensions
    if ext in {".py", ".js", ".ts", ".go", ".java", ".cs", ".cpp", ".c", ".rs", ".rb", ".php", ".kt", ".swift"}:
        score += 30

    lines = content.splitlines() if content else []
    loc = len(lines)

    # Boost for files with meaningful size
    if 20 <= loc <= 500:
        score += 20
    elif loc > 500:
        score += 10

    # Boost for complexity signals in content
    complexity_keywords = (
        "class ", "def ", "function ", "async ", "await ",
        "algorithm", "cache", "queue", "stack", "tree", "graph",
        "sort", "search", "parse", "validate", "compute", "process",
        "raise ", "except ", "try:", "finally:",
    )
    keyword_hits = sum(1 for kw in complexity_keywords if kw in content)
    score += min(keyword_hits * 3, 30)

    # Slight deprioritize for test files (still useful but not primary logic)
    if any(t in path_lower for t in ("test", "spec", "mock", "fixture")):
        score -= 15

    return max(0, score)


def _make_structural_summary(path: str, content: str) -> str:
    """
    For files that don't fit as full snippets, extract a compact structural
    summary: class names, function signatures, key imports.
    Much smaller than the full file but preserves architectural signal.
    """
    lines = (content or "").splitlines()
    summary_lines = []

    for line in lines:
        stripped = line.strip()
        if any(stripped.startswith(kw) for kw in (
            "class ", "def ", "async def ", "function ", "const ", "let ", "var ",
            "import ", "from ", "export ", "module ", "interface ", "type ",
            "struct ", "enum ", "fn ", "pub fn ", "pub struct ", "pub enum ",
            "@", "//", "#!",
        )):
            summary_lines.append(line)

    if not summary_lines:
        return f"[{path}: {len(lines)} lines, no extractable structure]"

    summary = "\n".join(summary_lines[:60])  # cap at 60 structural lines
    return f"[SUMMARY of {path} ({len(lines)} lines total)]\n{summary}"


def _build_smart_payload(
    raw_files: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Given all files, returns (primary_batch, overflow_batch).

    primary_batch: files that fit within the token budget.
      - High-priority files included with full content.
      - Files that don't fit get structural summaries (signatures only).
      - Boilerplate (configs, lockfiles, assets) dropped entirely.

    overflow_batch: high-priority files deferred because even their summary
      didn't fit. A second LLM call is made for these and results are merged.

    This ensures we NEVER blindly truncate mid-file. Every file is either:
      - Included fully           (high priority, fits in budget)
      - Included as a summary    (medium/high priority, full didn't fit)
      - Deferred to batch 2      (high priority, summary also didn't fit)
      - Dropped entirely         (low priority boilerplate)
    """
    budget = _payload_char_budget()

    # Score and sort all files highest-priority first
    scored = []
    for f in raw_files:
        content = f.get("snippet", "")
        priority = _file_priority_score(f.get("path", ""), content)
        scored.append((priority, f, content))
    scored.sort(key=lambda x: x[0], reverse=True)

    primary: List[Dict[str, Any]] = []
    overflow: List[Dict[str, Any]] = []
    used_chars = 0

    for priority, f, content in scored:
        if priority == 0:
            continue  # drop boilerplate entirely

        path = f.get("path", "")

        if used_chars + len(content) <= budget:
            # Full content fits — include as-is
            primary.append({"path": path, "snippet": content, "_included": "full"})
            used_chars += len(content)
        else:
            # Full doesn't fit — try a structural summary
            summary = _make_structural_summary(path, content)
            if used_chars + len(summary) <= budget:
                primary.append({"path": path, "snippet": summary, "_included": "summary"})
                used_chars += len(summary)
            elif priority >= 50:
                # High-priority file that can't even fit a summary — defer
                overflow.append({"path": path, "snippet": content, "_included": "full"})

    included_full = sum(1 for f in primary if f.get("_included") == "full")
    included_summary = sum(1 for f in primary if f.get("_included") == "summary")
    logger.info(
        "Payload built: %d full + %d summaries in primary batch, %d deferred to overflow. "
        "Budget used: %d/%d chars (~%d/%d tokens)",
        included_full, included_summary, len(overflow),
        used_chars, budget,
        used_chars // _CHARS_PER_TOKEN, budget // _CHARS_PER_TOKEN,
    )

    # Strip internal metadata key before sending to LLM
    clean_primary = [{"path": f["path"], "snippet": f["snippet"]} for f in primary]
    clean_overflow = [{"path": f["path"], "snippet": f["snippet"]} for f in overflow]
    return clean_primary, clean_overflow


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

def try_repair_truncated_json(text: str) -> dict:
    return {}

def _extract_json_payload(text: str) -> dict:
    if not text or not text.strip():
        logger.warning("LLM returned empty text, nothing to parse")
        return {}

    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except Exception:
        pass

    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence_match:
        try:
            result = json.loads(fence_match.group(1).strip())
            if isinstance(result, dict):
                return result
        except Exception:
            pass

    # Balanced-brace extraction
    start = text.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start=start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        result = json.loads(text[start: i + 1])
                        if isinstance(result, dict):
                            return result
                    except Exception:
                        break

    # Before giving up, attempt repair
    repaired = try_repair_truncated_json(text)
    if repaired:
        logging.info("Repaired partial JSON, recovered keys: %s", list(repaired.keys()))
        return repaired  # use whatever keys were complete
    logging.warning("JSON repair failed, returning empty dict")
    return {}


# ---------------------------------------------------------------------------
# HTTP helpers with retry
# ---------------------------------------------------------------------------

def _post_with_retry(
    url: str,
    body: dict,
    headers: dict | None = None,
    max_retries: int = 3,
) -> dict:
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            with httpx.Client(timeout=_llm_timeout()) as client:
                r = client.post(url, json=body, headers=headers or {})
                r.raise_for_status()
                return r.json()
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_exc = e
            wait = 2 ** (attempt - 1)
            logger.warning("LLM request attempt %d/%d failed (%s), retrying in %ds", attempt, max_retries, e, wait)
            time.sleep(wait)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (429, 502, 503):
                last_exc = e
                wait = 2 ** (attempt - 1)
                logger.warning("LLM HTTP %d attempt %d/%d, retrying in %ds", e.response.status_code, attempt, max_retries, wait)
                time.sleep(wait)
            else:
                raise LLMError(f"HTTP {e.response.status_code}: {e.response.text[:200]}") from e
        except Exception as e:
            raise LLMError(f"Unexpected error: {e}") from e

    raise LLMError(f"All {max_retries} attempts failed. Last error: {last_exc}")


def _extract_openrouter_resp(jr: dict) -> dict:
    if not isinstance(jr, dict):
        logger.warning("OpenRouter response is not a dict: %r", jr)
        return {}

    if "error" in jr and "choices" not in jr:
        err = jr["error"]
        msg = err.get("message", "") if isinstance(err, dict) else str(err)
        code = err.get("code", "") if isinstance(err, dict) else ""
        msg_lower = msg.lower()
        if any(kw in msg_lower for kw in ("context length", "maximum context", "input tokens", "too long")):
            logger.warning("Context-length error from provider: %s", msg[:300])
        else:
            logger.warning("Provider error (code=%s): %s", code, msg[:200])
        return {}

    choices = jr.get("choices")
    if not choices:
        logger.warning("OpenRouter response has no choices: %r", jr)
        return {}

    message = choices[0].get("message", {})
    text = message.get("content") or choices[0].get("text") or ""

    if not text:
        logger.warning("OpenRouter choice has empty content. Full response: %r", jr)
        return {}

    logger.debug("LLM raw response: %s", text[:500])
    parsed = _extract_json_payload(text)
    if not parsed:
        logger.warning("JSON extraction returned empty dict from text: %r", text[:300])
    return parsed


# ---------------------------------------------------------------------------
# Learning resource ranking helpers
# ---------------------------------------------------------------------------

def _is_valid_learning_rank(resp: dict) -> bool:
    if not resp or "ranked" not in resp:
        return False
    ranked = resp.get("ranked")
    if not isinstance(ranked, list):
        return False
    return all(isinstance(item, dict) and item.get("id") for item in ranked)


def _deterministic_learning_rank(payload: dict) -> dict:
    resources = payload.get("resources") if isinstance(payload, dict) else []
    if not isinstance(resources, list):
        resources = []

    def _score(item: dict) -> float:
        try:
            return float(item.get("score", 0.0) or 0.0)
        except Exception:
            return 0.0

    ordered = sorted(
        (r for r in resources if isinstance(r, dict) and r.get("id")),
        key=lambda r: (_score(r), str(r.get("id"))),
        reverse=True,
    )

    return {
        "ranked": [
            {
                "id": r.get("id"),
                "explanation": "Ranked by semantic relevance, quality, and fit.",
            }
            for r in ordered
        ]
    }


def _call_learning_rank_once(payload: dict, ai_mode: str) -> dict:
    if ai_mode == "ollama":
        url, model = _ollama_config()
        body = {
            "model": model,
            "task": "learning_resource_ranking",
            "payload": payload,
            "response_format": "json",
            "instructions": (
                "Return JSON with key 'ranked' containing a list of objects with: "
                "id (string), explanation (string), expected_gain (optional int). "
                "Rank by relevance to issues, quality, and difficulty fit."
            ),
        }
        jr = _post_with_retry(f"{url.rstrip('/')}/llm", body, max_retries=2)
        return jr if isinstance(jr, dict) else {}

    url, key, model = _openrouter_config()
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return only strict JSON. No markdown. No extra keys."},
            {
                "role": "user",
                "content": (
                    "You are ranking learning resources for a developer based on analysis results.\n\n"
                    "Return ONLY a JSON object with this exact structure:\n\n"
                    "{\n"
                    "  \"ranked\": [\n"
                    "    {\"id\": \"...\", \"explanation\": \"...\", \"expected_gain\": 0-20}\n"
                    "  ]\n"
                    "}\n\n"
                    "Rules:\n"
                    "- Use only resource IDs provided in the input.\n"
                    "- Sort most relevant first.\n"
                    "- Explanation: 1 sentence, concrete, no fluff.\n"
                    "- expected_gain is optional; omit if unsure.\n\n"
                    "Input:\n"
                    f"{json.dumps(payload)}"
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    jr = _post_with_retry(f"{url.rstrip('/')}/chat/completions", body, headers=headers, max_retries=2)
    return _extract_openrouter_resp(jr)


# ---------------------------------------------------------------------------
# Evidence-based skill gap analysis
# ---------------------------------------------------------------------------

SKILL_TAXONOMY = [
    "Unit Testing",
    "Test Design",
    "Mocking",
    "Refactoring",
    "Clean Code",
    "SOLID Principles",
    "Separation of Concerns",
    "Secure Coding",
    "OWASP Top 10",
    "Dependency Management",
    "Input Validation",
    "DRY Principle",
    "Design Patterns",
]

_PRIORITY_ALIASES = {
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}


def _short_text(value: object, max_len: int = 180) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:max_len].rstrip()


def _clamp_confidence(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return round(max(0.0, min(1.0, number)), 3)


def _normalise_priority(value: object) -> str:
    return _PRIORITY_ALIASES.get(str(value or "").strip().lower(), "Low")


def _validate_skill_gaps(resp: dict, allowed_skills: list[str]) -> list[dict]:
    if not isinstance(resp, dict):
        return []
    raw_gaps = resp.get("skill_gaps")
    if not isinstance(raw_gaps, list):
        return []

    allowed = set(allowed_skills)
    validated: list[dict] = []
    seen: set[str] = set()
    for item in raw_gaps:
        if not isinstance(item, dict):
            continue
        skill = _short_text(item.get("skill"), 80)
        if skill not in allowed or skill in seen:
            continue
        evidence = item.get("evidence")
        if not isinstance(evidence, list):
            continue
        clean_evidence = []
        for entry in evidence:
            text = _short_text(entry, 160)
            if text:
                clean_evidence.append(text)
        clean_evidence = list(dict.fromkeys(clean_evidence))[:4]
        if not clean_evidence:
            continue
        related_metrics = item.get("related_metrics")
        if not isinstance(related_metrics, list):
            related_metrics = []
        validated.append({
            "skill": skill,
            "priority": _normalise_priority(item.get("priority")),
            "confidence": _clamp_confidence(item.get("confidence")),
            "reason": _short_text(item.get("reason"), 220),
            "evidence": clean_evidence,
            "related_metrics": [
                _short_text(metric, 60)
                for metric in related_metrics
                if _short_text(metric, 60)
            ][:6],
        })
        seen.add(skill)
    return validated


def _call_skill_gaps_once(payload: dict, ai_mode: str) -> dict:
    if ai_mode == "ollama":
        url, model = _ollama_config()
        body = {
            "model": model,
            "task": "sonarqube_skill_gap_analysis",
            "payload": payload,
            "response_format": "json",
            "instructions": (
                "Return only raw valid JSON with key skill_gaps. Choose only from allowed_skills. "
                "Base gaps only on the provided metrics, file metrics, issues, and security findings. "
                "Include evidence for every selected gap. Return an empty skill_gaps list when the input does not justify a gap."
            ),
        }
        jr = _post_with_retry(f"{url.rstrip('/')}/llm", body, max_retries=2)
        return jr if isinstance(jr, dict) else {}

    url, key, model = _openrouter_config()
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return only raw valid JSON. No markdown. No extra keys."},
            {
                "role": "user",
                "content": (
                    "You are an evidence-based developer skill gap judge.\n\n"
                    "Your task is to inspect the provided analysis input and select only the skill gaps that are directly supported by evidence.\n"
                    "Return only raw valid JSON with this structure:\n"
                    "{\n"
                    "  \"skill_gaps\": [\n"
                    "    {\n"
                    "      \"skill\": \"<exact skill from allowed_skills>\",\n"
                    "      \"priority\": \"High|Medium|Low\",\n"
                    "      \"confidence\": 0.0,\n"
                    "      \"reason\": \"Short explanation grounded in the input.\",\n"
                    "      \"evidence\": [\"Short evidence item from the input\"],\n"
                    "      \"related_metrics\": [\"metric_name\"]\n"
                    "    }\n"
                    "  ]\n"
                    "}\n\n"
                    "Selection rules:\n"
                    "- Choose skills only from allowed_skills.\n"
                    "- Do not invent, rename, or generalize skill names.\n"
                    "- Select a skill only when the provided metrics, file metrics, issues, or security findings support it.\n"
                    "- Every selected skill must include concrete evidence copied or summarized from the input.\n"
                    "- If the input does not justify a skill gap, return {\"skill_gaps\": []}.\n"
                    "- Priority must be one of High, Medium, or Low.\n"
                    "- Confidence must be a number between 0 and 1.\n"
                    "- Do not add fields outside the requested JSON structure.\n\n"
                    "Input:\n"
                    f"{json.dumps(payload)}"
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 2500,
        "temperature": 0.1,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    jr = _post_with_retry(f"{url.rstrip('/')}/chat/completions", body, headers=headers, max_retries=2)
    return _extract_openrouter_resp(jr)


def analyze_skill_gaps_with_llm(
    sonar_metrics: dict,
    sonar_file_metrics: list[dict],
    sonar_issues: list[dict],
    security_findings: list[dict],
    allowed_skills: list[str] | None = None,
) -> dict:
    taxonomy = [
        skill for skill in (allowed_skills or SKILL_TAXONOMY)
        if skill in set(SKILL_TAXONOMY)
    ]
    if not taxonomy:
        taxonomy = list(SKILL_TAXONOMY)

    payload = {
        "allowed_skills": taxonomy,
        "sonar_metrics": sonar_metrics if isinstance(sonar_metrics, dict) else {},
        "sonar_file_metrics": sonar_file_metrics[:30] if isinstance(sonar_file_metrics, list) else [],
        "sonar_issues": sonar_issues[:50] if isinstance(sonar_issues, list) else [],
        "security_findings": security_findings[:50] if isinstance(security_findings, list) else [],
    }

    try:
        ai_mode = (os.environ.get("AI_MODE") or "openrouter").lower()
        resp = _call_skill_gaps_once(payload, ai_mode)
        return {"skill_gaps": _validate_skill_gaps(resp, taxonomy)}
    except Exception as exc:
        logger.warning("skill_gap_analysis failed; continuing without LLM gaps: %s", exc)
        return {"skill_gaps": []}


REPOSITORY_MANAGER_RECOMMENDATION_KEYS = (
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

REPOSITORY_MANAGER_RECOMMENDATION_PROMPT = """You are an engineering manager advisor reviewing ONE selected repository only.

You must generate repository-specific recommendations based strictly on the supplied payload.
Do not use generic engineering advice.
Do not repeat the same recommendation across buckets.
Do not invent metrics, files, risks, or scores.
Do not mention a metric unless it exists in the payload.
Every recommendation must be caused by an actual repository-specific signal such as low coverage, bugs, code smells, security findings, failed quality gate, duplication, high complexity, risky files, or strong scores.

Return ONLY valid JSON with exactly these keys:
fix_first, prioritize_next, plan_when_possible, strengthen_further, architectural_concerns, delivery_risks, quality_concerns, team_strengths, recommended_priorities.

Bucket meaning:
- fix_first: urgent issues that create release, security, regression, or production risk.
- prioritize_next: important but not immediately blocking quality or maintainability improvements.
- plan_when_possible: lower urgency improvements that should be scheduled later.
- strengthen_further: repository strengths worth preserving or scaling.
- architectural_concerns: architecture or complexity risks grounded in files/metrics.
- delivery_risks: risks that could affect release confidence or delivery speed.
- quality_concerns: quality issues grounded in Sonar/code metrics.
- team_strengths: positive repository/team signals from the selected repository only.
- recommended_priorities: concise ordered manager actions.

Rules:
- If a bucket has no real evidence, return an empty array.
- Keep each item concise and manager-facing.
- Prefer specific file names when available.
- Include exact metric values when useful.
- Never output "No recommendation generated."
- Never copy the same sentence into multiple repositories unless the underlying repository metrics are genuinely identical.
- Never use all-repository/team-wide data for a repository-specific recommendation.
"""


def _empty_repository_manager_recommendations() -> dict[str, list[str]]:
    return {key: [] for key in REPOSITORY_MANAGER_RECOMMENDATION_KEYS}


def _validate_repository_manager_recommendations(resp: dict) -> dict[str, list[str]]:
    if not isinstance(resp, dict):
        return _empty_repository_manager_recommendations()

    clean: dict[str, list[str]] = {}
    for key in REPOSITORY_MANAGER_RECOMMENDATION_KEYS:
        value = resp.get(key)
        if not isinstance(value, list):
            clean[key] = []
            continue
        items: list[str] = []
        for item in value:
            text = _short_text(item, 260)
            if text:
                items.append(text)
        clean[key] = list(dict.fromkeys(items))
    return clean


def _call_repository_manager_recommendations_once(payload: dict, ai_mode: str) -> dict:
    if ai_mode == "ollama":
        url, model = _ollama_config()
        body = {
            "model": model,
            "task": "repository_manager_recommendations",
            "payload": payload,
            "response_format": "json",
            "instructions": REPOSITORY_MANAGER_RECOMMENDATION_PROMPT,
        }
        jr = _post_with_retry(f"{url.rstrip('/')}/llm", body, max_retries=2)
        return jr if isinstance(jr, dict) else {}

    url, key, model = _openrouter_config()
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return only strict JSON. No markdown. No extra keys."},
            {
                "role": "user",
                "content": (
                    f"{REPOSITORY_MANAGER_RECOMMENDATION_PROMPT}\n\n"
                    "Payload:\n"
                    f"{json.dumps(payload, ensure_ascii=False)}"
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 2500,
        "temperature": 0.1,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    jr = _post_with_retry(f"{url.rstrip('/')}/chat/completions", body, headers=headers, max_retries=2)
    return _extract_openrouter_resp(jr)


def generate_repository_manager_recommendations(payload: dict) -> dict:
    """
    Generate manager dashboard recommendations for one selected repository.
    Invalid, missing, or failed LLM output is normalized to empty buckets only.
    """
    if not isinstance(payload, dict) or not payload.get("repository"):
        return _empty_repository_manager_recommendations()

    try:
        ai_mode = (os.environ.get("AI_MODE") or "openrouter").lower()
        resp = _call_repository_manager_recommendations_once(payload, ai_mode)
        return _validate_repository_manager_recommendations(resp)
    except Exception as exc:
        logger.warning("repository_manager_recommendations failed; returning empty buckets: %s", exc)
        return _empty_repository_manager_recommendations()


def rank_learning_resources(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Rank learning resources with LLM guidance and a deterministic fallback.
    """
    if not isinstance(payload, dict):
        return {"ranked": []}

    fallback = _deterministic_learning_rank(payload)
    resources = payload.get("resources")
    if not isinstance(resources, list) or not resources:
        return fallback

    ai_mode = (os.environ.get("AI_MODE") or "openrouter").lower()
    max_retries = _max_retries()

    resp = {}
    for attempt in range(1, max_retries + 1):
        try:
            resp = _call_learning_rank_once(payload, ai_mode)
        except LLMError as exc:
            logger.warning("learning_rank attempt %d/%d failed: %s", attempt, max_retries, exc)
            resp = {}

        if _is_valid_learning_rank(resp):
            return resp

        logger.warning("learning_rank attempt %d/%d returned invalid payload", attempt, max_retries)
        resp = {}
        if attempt < max_retries:
            time.sleep(2 ** (attempt - 1))

    return fallback
