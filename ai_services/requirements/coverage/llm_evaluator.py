"""LLM-based AC coverage evaluation."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv

    _ROOT = Path(__file__).resolve().parents[3]
    load_dotenv(_ROOT / "backend" / ".env")
    load_dotenv(_ROOT / ".env")
except Exception:
    pass


def _coverage_llm_config() -> tuple[str, str, str | None, str]:
    mode = (os.environ.get("AI_MODE") or os.environ.get("ai_mode") or "ollama").lower()
    if mode == "openrouter":
        url = os.environ.get("OPENROUTER_API_URL") or os.environ.get("openrouter_api_url") or "https://openrouter.ai/api/v1"
        key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("openrouter_api_key") or ""
        model = os.environ.get("OPENROUTER_MODEL") or os.environ.get("openrouter_model")
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY required for coverage LLM")
        if not model:
            raise RuntimeError("OPENROUTER_MODEL required for coverage LLM")
        return f"{url.rstrip('/')}/chat/completions", model, key, "openai_compatible"
    url = os.environ.get("OLLAMA_BASE_URL") or os.environ.get("ollama_base_url") or "http://localhost:11434/v1"
    model = os.environ.get("OLLAMA_MODEL") or os.environ.get("ollama_model") or "qwen3:14b"
    return f"{url.rstrip('/')}/chat/completions", model, None, "ollama"


def _format_evidence_blocks(code_evidence: list[dict]) -> str:
    evidence_blocks = []
    for i, chunk in enumerate(code_evidence, 1):
        evidence_blocks.append(
            f"--- Chunk {i} ({chunk.get('file_path')}, lines {chunk.get('start_line')}-{chunk.get('end_line')}) ---\n"
            f"{chunk.get('chunk_text', '')[:2500]}"
        )
    return "\n\n".join(evidence_blocks) if evidence_blocks else "(no code evidence retrieved)"


def _build_prompt(
    *,
    story_title: str,
    story_description: str,
    ac_text: str,
    code_evidence: list[dict],
) -> str:
    evidence_text = _format_evidence_blocks(code_evidence)

    return f"""You are evaluating project readiness for acceptance criteria in a codebase.

User story: {story_title}
Description: {story_description}

Acceptance criterion to evaluate:
{ac_text}

Retrieved code evidence:
{evidence_text}

Respond with JSON only:
{{
  "status": "COVERED" | "PARTIALLY_COVERED" | "NOT_COVERED",
  "confidence": 0.0 to 1.0,
  "reason": "brief explanation citing files/symbols if possible"
}}

Rules:
- Evaluate readiness, not simple code presence.
- COVERED: the acceptance criterion is implemented as a usable feature. Evidence demonstrates the required workflow end-to-end. No major placeholder, mocked, hardcoded, static, or obviously incomplete implementation remains. Backend, frontend, API flow, persistence, and user interaction must be present when they are required by the acceptance criterion.
- PARTIALLY_COVERED: core implementation exists, but important workflow pieces are missing, incomplete, hardcoded, mocked, static, placeholder-based, or only partially integrated. The feature demonstrates progress but is not fully ready.
- NOT_COVERED: the required behavior is absent or unsupported by meaningful evidence.
- If evidence only shows isolated service/model/endpoint/test code but not a usable workflow required by the AC, choose PARTIALLY_COVERED rather than COVERED.
- If evidence includes hardcoded sample data, placeholder objects, mocked behavior, static UI, or missing integration for a required workflow, choose PARTIALLY_COVERED unless the missing piece is clearly irrelevant to the AC.
- Do not infer readiness beyond the retrieved evidence. If an end-to-end piece is required by the AC but not shown in evidence, treat it as missing or incomplete.
""" 


def _build_developer_task_prompt(
    *,
    task_description: str,
    linked_acceptance_criteria: list[str],
    code_evidence: list[dict],
) -> str:
    evidence_text = _format_evidence_blocks(code_evidence)
    linked_ac_text = "\n".join(f"- {text}" for text in linked_acceptance_criteria if text.strip())
    if not linked_ac_text:
        linked_ac_text = "(no linked acceptance criteria provided)"

    return f"""You are evaluating implementation progress for one assigned developer technical task.

Assigned technical task:
{task_description}

Linked acceptance criteria for context only:
{linked_ac_text}

Retrieved code evidence:
{evidence_text}

Respond with JSON only:
{{
  "status": "COVERED" | "PARTIALLY_COVERED" | "NOT_COVERED",
  "confidence": 0.0 to 1.0,
  "reason": "brief explanation citing files/symbols if possible"
}}

Rules:
- Evaluate only whether the assigned technical task has been implemented.
- Do not evaluate business requirement coverage, story readiness, deployment readiness, or unrelated tasks.
- Linked acceptance criteria are context only. Do not require unrelated AC workflow pieces that are outside the assigned task scope.
- COVERED: the assigned task is implemented and usable. Evidence demonstrates the expected task behavior. No major placeholder, mocked, hardcoded, static, pass-only, TODO, or obviously incomplete implementation remains. The implementation required by the task exists and is operational.
- PARTIALLY_COVERED: core implementation exists, but important logic is missing, integration is incomplete, placeholder code exists, hardcoded behavior exists, or implementation is only partially functional. The task shows progress but is not fully completed.
- NOT_COVERED: the required task behavior is absent. Evidence does not demonstrate meaningful implementation. Only declarations, interfaces, models, routes, schemas, stubs, placeholders, or unrelated code are present.
- Do not fail this task because another assigned task is incomplete. Example: if the task is "Build Export Report Button" and the button implementation exists and functions correctly, choose COVERED even if PDF generation belongs to another task.
- If the evidence is ambiguous or only shows scaffolding around the task, choose PARTIALLY_COVERED or NOT_COVERED rather than inferring completion.
"""


def _parse_llm_json(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("No JSON object in LLM response")
    data = json.loads(match.group())
    status = data.get("status", "NOT_COVERED")
    if status not in {"COVERED", "PARTIALLY_COVERED", "NOT_COVERED"}:
        status = "NOT_COVERED"
    confidence = float(data.get("confidence", 0.5))
    confidence = max(0.0, min(1.0, confidence))
    return {
        "status": status,
        "confidence": confidence,
        "reason": str(data.get("reason") or ""),
    }


async def evaluate_ac_coverage(
    *,
    story_title: str,
    story_description: str,
    ac_text: str,
    code_evidence: list[dict],
) -> dict:
    if not ac_text.strip():
        return {"status": "NOT_COVERED", "confidence": 1.0, "reason": "Empty acceptance criterion"}

    endpoint, model, api_key, provider = _coverage_llm_config()
    prompt = _build_prompt(
        story_title=story_title,
        story_description=story_description,
        ac_text=ac_text,
        code_evidence=code_evidence,
    )
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }

    try:
        body = await _post_llm_chat(
            endpoint=endpoint,
            provider=provider,
            headers=headers,
            payload=payload,
            model=model,
            prompt=prompt,
        )
        content = _extract_chat_content(body)
        return _parse_llm_json(content)
    except Exception as exc:
        logger.warning("AC evaluation LLM failed: %s", exc)
        if not code_evidence:
            return {"status": "NOT_COVERED", "confidence": 0.3, "reason": f"No evidence; LLM error: {exc}"}
        return {"status": "PARTIALLY_COVERED", "confidence": 0.3, "reason": f"LLM evaluation failed: {exc}"}


async def evaluate_developer_task_implementation(
    *,
    task_description: str,
    linked_acceptance_criteria: list[str] | None,
    code_evidence: list[dict],
) -> dict:
    if not task_description.strip():
        return {"status": "NOT_COVERED", "confidence": 1.0, "reason": "Empty technical task"}

    endpoint, model, api_key, provider = _coverage_llm_config()
    prompt = _build_developer_task_prompt(
        task_description=task_description,
        linked_acceptance_criteria=linked_acceptance_criteria or [],
        code_evidence=code_evidence,
    )
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }

    try:
        body = await _post_llm_chat(
            endpoint=endpoint,
            provider=provider,
            headers=headers,
            payload=payload,
            model=model,
            prompt=prompt,
        )
        content = _extract_chat_content(body)
        return _parse_llm_json(content)
    except Exception as exc:
        logger.warning("Developer task evaluation LLM failed: %s", exc)
        if not code_evidence:
            return {"status": "NOT_COVERED", "confidence": 0.3, "reason": f"No evidence; LLM error: {exc}"}
        return {"status": "PARTIALLY_COVERED", "confidence": 0.3, "reason": f"LLM evaluation failed: {exc}"}


async def _post_llm_chat(
    *,
    endpoint: str,
    provider: str,
    headers: dict,
    payload: dict,
    model: str,
    prompt: str,
) -> dict:
    try:
        return await _post_llm_chat_once(
            endpoint=endpoint,
            provider=provider,
            headers=headers,
            payload=payload,
            model=model,
            prompt=prompt,
            verify=True,
        )
    except httpx.ConnectError as exc:
        if not _is_certificate_error(exc) or not _allow_insecure_ssl_retry():
            raise
        logger.warning("Coverage LLM TLS verification failed; retrying without verification in development mode")
        return await _post_llm_chat_once(
            endpoint=endpoint,
            provider=provider,
            headers=headers,
            payload=payload,
            model=model,
            prompt=prompt,
            verify=False,
        )


async def _post_llm_chat_once(
    *,
    endpoint: str,
    provider: str,
    headers: dict,
    payload: dict,
    model: str,
    prompt: str,
    verify: bool,
) -> dict:
    async with httpx.AsyncClient(timeout=120.0, verify=verify) as client:
        resp = await client.post(endpoint, headers=headers, json=payload)
        if provider == "ollama" and resp.status_code == 404:
            ollama_endpoint = _ollama_native_endpoint(endpoint)
            ollama_payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.1},
            }
            resp = await client.post(ollama_endpoint, headers={"Content-Type": "application/json"}, json=ollama_payload)
        resp.raise_for_status()
        return resp.json()


def _is_certificate_error(exc: Exception) -> bool:
    return "CERTIFICATE_VERIFY_FAILED" in str(exc) or "certificate verify failed" in str(exc).lower()


def _allow_insecure_ssl_retry() -> bool:
    raw = (
        os.environ.get("COVERAGE_LLM_ALLOW_INSECURE_SSL")
        or os.environ.get("LLM_ALLOW_INSECURE_SSL")
        or ""
    ).lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    return (os.environ.get("ENVIRONMENT") or "").lower() in {"dev", "development", "local"}


def _ollama_native_endpoint(openai_endpoint: str) -> str:
    base = openai_endpoint.rstrip("/")
    if base.endswith("/v1/chat/completions"):
        base = base[: -len("/v1/chat/completions")]
    elif base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")]
    if base.endswith("/v1"):
        base = base[:-3]
    return f"{base.rstrip('/')}/api/chat"


def _extract_chat_content(body: dict) -> str:
    if "choices" in body:
        return body["choices"][0]["message"]["content"]
    if "message" in body and isinstance(body["message"], dict):
        return str(body["message"].get("content") or "")
    if "response" in body:
        return str(body.get("response") or "")
    raise ValueError("Unsupported LLM response shape")
