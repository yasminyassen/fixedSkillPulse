"""Deterministic coverage scoring (no confidence in formulas)."""

from __future__ import annotations

AC_STATUS_SCORES = {
    "COVERED": 1.0,
    "PARTIALLY_COVERED": 0.5,
    "NOT_COVERED": 0.0,
}

PRIORITY_WEIGHTS = {
    "critical": 1.0,
    "high": 0.8,
    "medium": 0.6,
    "low": 0.4,
}


def ac_score_from_status(status: str) -> float:
    return AC_STATUS_SCORES.get(status, 0.0)


def story_coverage_score(ac_statuses: list[str]) -> float:
    if not ac_statuses:
        return 0.0
    total = sum(ac_score_from_status(s) for s in ac_statuses)
    return round(total / len(ac_statuses), 4)


def story_coverage_status(score: float, ac_statuses: list[str] | None = None) -> str:
    statuses = ac_statuses or []
    has_covered = any(status == "COVERED" for status in statuses)
    has_partial = any(status == "PARTIALLY_COVERED" for status in statuses)
    has_missing = any(status == "NOT_COVERED" for status in statuses)

    if score >= 0.85 and not has_partial and not has_missing:
        return "implemented"
    if score >= 0.25 or has_covered or has_partial:
        return "partially_implemented"
    return "not_implemented"


def overall_coverage_score(story_scores: list[tuple[float, str]]) -> float:
    """Weighted average using story priority."""
    if not story_scores:
        return 0.0
    weighted = 0.0
    weight_sum = 0.0
    for score, priority in story_scores:
        w = PRIORITY_WEIGHTS.get((priority or "medium").lower(), 0.6)
        weighted += score * w
        weight_sum += w
    if weight_sum == 0:
        return 0.0
    return round(weighted / weight_sum, 4)


def build_task_embedding_text(
    *,
    story_title: str,
    story_description: str,
    task_description: str,
    ac_texts: list[str],
) -> str:
    parts = [
        f"User story: {story_title}",
        f"Description: {story_description}",
        f"Technical task: {task_description}",
    ]
    if ac_texts:
        parts.append("Linked acceptance criteria:\n" + "\n".join(f"- {t}" for t in ac_texts))
    return "\n".join(parts)


def ac_text_by_id(acceptance_criteria: list, ac_id: int) -> str:
    for ac in acceptance_criteria or []:
        if isinstance(ac, dict) and ac.get("id") == ac_id:
            return ac.get("text") or ""
        if isinstance(ac, str):
            continue
    return ""


def tasks_for_ac(tasks: list, ac_id: int) -> list:
    linked = []
    for task in tasks:
        ac_ids = task.ac_ids if hasattr(task, "ac_ids") else task.get("ac_ids", [])
        if ac_ids and ac_id in ac_ids:
            linked.append(task)
    return linked
