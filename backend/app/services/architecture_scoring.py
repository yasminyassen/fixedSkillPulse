"""Architecture scoring pipeline with strict scoring-authority separation.

Layers:
  1. Static analyzer  → signals, structural indices, constraints (never final scores)
  2. LLM evaluator    → raw scores + evidence (never final scores)
  3. Aggregator       → sole authority for final per-metric and overall scores
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

ARCHITECTURE_METRIC_KEYS = (
    "layer_count_srp",
    "repository_pattern",
    "dependency_injection",
    "circular_imports",
    "open_closed_readiness",
    "swappable_components",
    "module_decomposition",
    "god_class_function",
    "coupling",
    "cohesion",
)

METRIC_WEIGHT = 1.0 / len(ARCHITECTURE_METRIC_KEYS)

METRIC_METHODS: dict[str, str] = {
    "layer_count_srp": "LLM",
    "repository_pattern": "LLM",
    "dependency_injection": "LLM",
    "circular_imports": "pydeps + import-linter",
    "open_closed_readiness": "LLM",
    "swappable_components": "LLM",
    "module_decomposition": "LLM + AST",
    "god_class_function": "LLM + AST (radon)",
    "coupling": "LLM + AST",
    "cohesion": "LLM",
}

HYBRID_STRUCTURAL_WEIGHT = 0.35
HYBRID_LLM_WEIGHT = 0.65

SCORE_UNCERTAIN_DEFAULT = 30.0
CAP_SEVERE_MAX = 18.0
CAP_ABSENT_SOFT_CEILING = 35.0
CAP_ABSENT_INDIRECT_MAX = 45.0
NEUTRAL_SCORE_BAND = (48.0, 52.0)

LLM_ONLY_METRICS = frozenset({
    "layer_count_srp",
    "repository_pattern",
    "dependency_injection",
    "open_closed_readiness",
    "swappable_components",
    "cohesion",
})

HYBRID_METRICS = frozenset({
    "module_decomposition",
    "coupling",
    "god_class_function",
})


@dataclass
class MetricConstraints:
    """Non-authoritative caps produced by static analysis for the aggregator."""

    cap_severe: bool = False
    cap_absent_soft: bool = False
    indirect_structural_evidence: bool = False
    structural_index: float | None = None


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def _normalize(value: float, low: float, high: float, reverse: bool = False) -> float:
    if high <= low:
        return 100.0
    scaled = max(0.0, min(1.0, (value - low) / (high - low)))
    if reverse:
        scaled = 1.0 - scaled
    return scaled * 100.0


def _avg_normalized(
    file_reports: list[dict],
    key: str,
    low: float,
    high: float,
    reverse: bool = False,
) -> float:
    values = [float(r["metrics"].get(key, 0.0)) for r in file_reports]
    if not values:
        return 0.0
    return sum(_normalize(v, low, high, reverse=reverse) for v in values) / len(values)


# ---------------------------------------------------------------------------
# Static layer — signals and structural indices only (NOT final scores)
# ---------------------------------------------------------------------------


def _build_static_signals(
    file_reports: list[dict],
    aggregate_metrics: dict,
) -> dict[str, Any]:
    inline_business = int(
        sum(int(r["metrics"].get("inline_concrete_instantiations_business", 0)) for r in file_reports)
    )
    inline_total = int(
        sum(int(r["metrics"].get("inline_concrete_instantiations", 0)) for r in file_reports)
    )
    depends = int(sum(int(r["metrics"].get("depends_usage", 0)) for r in file_reports))
    repositories = int(sum(int(r["metrics"].get("repository_classes", 0)) for r in file_reports))
    abstractions = int(sum(int(r["metrics"].get("abstraction_signals", 0)) for r in file_reports))
    high_cc = int(sum(int(r["metrics"].get("high_cyclomatic_functions", 0)) for r in file_reports))
    long_fn = int(sum(int(r["metrics"].get("long_functions", 0)) for r in file_reports))
    file_count = len(file_reports)
    class_count = int(aggregate_metrics.get("class_count", 0))
    efferent = int(aggregate_metrics.get("efferent_coupling_total", 0))

    has_di = depends > 0
    has_abstractions = abstractions > 0 or repositories > 0
    has_direct_instantiation = inline_business > 0

    cap1_triad = has_direct_instantiation and not has_abstractions and not has_di

    pattern_evidence = {
        "repository_pattern": repositories > 0,
        "dependency_injection": has_di,
        "swappable_components": has_abstractions,
        "open_closed_readiness": abstractions > 0 or class_count >= 2,
        "layer_count_srp": file_count >= 2 or class_count >= 2,
        "cohesion": class_count >= 1 or file_count >= 2,
        "coupling": inline_business == 0 or has_abstractions,
        "module_decomposition": file_count >= 2,
        "god_class_function": high_cc == 0 and long_fn <= 2,
    }

    return {
        "inline_concrete_instantiations": inline_total,
        "inline_concrete_instantiations_business": inline_business,
        "depends_usage": depends,
        "repository_classes": repositories,
        "abstraction_signals": abstractions,
        "high_cyclomatic_functions": high_cc,
        "long_functions": long_fn,
        "file_count": file_count,
        "class_count": class_count,
        "efferent_coupling_total": efferent,
        "has_dependency_injection": has_di,
        "has_interfaces_or_abstractions": has_abstractions,
        "has_direct_instantiation_business_logic": has_direct_instantiation,
        "cap1_severe_triad": cap1_triad,
        "pattern_evidence": pattern_evidence,
    }


def compute_module_decomposition_index(file_reports: list[dict]) -> dict[str, Any]:
    """AST structural boundary index (0-100 hint, not a final score)."""
    if not file_reports:
        return {"structural_index": 0.0, "method": "AST", "details": {}}

    boundary_scores: list[float] = []
    for report in file_reports:
        metrics = report["metrics"]
        classes = float(metrics.get("class_count", 0))
        functions = float(metrics.get("function_count", 0))
        loc = max(float(metrics.get("loc", 0)), 1.0)
        symbols = classes + functions
        density = symbols / loc * 100.0

        if symbols <= 1:
            boundary_scores.append(0.45)
        elif density > 15.0:
            boundary_scores.append(max(0.2, 1.0 - density / 30.0))
        else:
            boundary_scores.append(min(1.0, 0.45 + classes * 0.12 + min(functions, 8.0) * 0.04))

    raw = sum(boundary_scores) / len(boundary_scores)
    return {
        "structural_index": _clamp_score(raw * 100.0),
        "method": "AST",
        "details": {
            "file_count": len(file_reports),
            "avg_boundary_score": round(raw, 3),
            "total_classes": int(sum(r["metrics"].get("class_count", 0) for r in file_reports)),
            "total_functions": int(sum(r["metrics"].get("function_count", 0) for r in file_reports)),
        },
    }


def compute_coupling_index(file_reports: list[dict], aggregate_metrics: dict) -> dict[str, Any]:
    """AST coupling index from business-logic inline instantiation (composition roots excluded)."""
    inline_score = _avg_normalized(
        file_reports, "inline_concrete_instantiations_business", 0.0, 6.0, reverse=True
    )
    efferent_score = _avg_normalized(file_reports, "efferent_coupling", 0.0, 12.0, reverse=True)
    total_inline_business = int(
        sum(int(r["metrics"].get("inline_concrete_instantiations_business", 0)) for r in file_reports)
    )
    total_efferent = int(aggregate_metrics.get("efferent_coupling_total", 0))
    index_value = (inline_score * 0.60) + (efferent_score * 0.40)
    return {
        "structural_index": _clamp_score(index_value),
        "method": "AST",
        "details": {
            "inline_concrete_instantiations_business": total_inline_business,
            "efferent_coupling_total": total_efferent,
            "import_coupling_total": int(aggregate_metrics.get("import_coupling_total", 0)),
        },
    }


def _run_radon_signals(repo_path: str, python_files: list[dict]) -> dict[str, Any]:
    paths = [
        os.path.join(repo_path, f["path"].replace("/", os.sep))
        for f in python_files
        if f.get("path")
    ]
    paths = [p for p in paths if os.path.isfile(p)]
    if not paths:
        return {"available": False, "high_complexity_blocks": 0, "max_complexity": 0}

    try:
        result = subprocess.run(
            ["radon", "cc", "-j", "-s", *paths[:40]],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=repo_path,
        )
        payload = json.loads(result.stdout) if result.stdout.strip() else {}
        high_complexity = 0
        max_cc = 0
        for file_blocks in payload.values():
            if not isinstance(file_blocks, list):
                continue
            for block in file_blocks:
                if not isinstance(block, dict):
                    continue
                cc = int(block.get("complexity", 0) or 0)
                max_cc = max(max_cc, cc)
                if cc >= 10:
                    high_complexity += 1
        return {
            "available": True,
            "high_complexity_blocks": high_complexity,
            "max_complexity": max_cc,
        }
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as exc:
        logger.warning("radon complexity unavailable: %s", exc)
        return {"available": False, "high_complexity_blocks": 0, "max_complexity": 0}


def compute_god_class_index(
    file_reports: list[dict],
    radon_signals: dict[str, Any],
) -> dict[str, Any]:
    """AST/radon complexity index (not a final score)."""
    high_cc = _avg_normalized(file_reports, "high_cyclomatic_functions", 0.0, 5.0, reverse=True)
    long_functions = _avg_normalized(file_reports, "long_functions", 0.0, 8.0, reverse=True)

    radon_index = None
    if radon_signals.get("available"):
        block_score = _normalize(radon_signals.get("high_complexity_blocks", 0), 0.0, 8.0, reverse=True)
        peak_score = _normalize(radon_signals.get("max_complexity", 0), 5.0, 25.0, reverse=True)
        radon_index = (block_score * 0.60) + (peak_score * 0.40)

    if radon_index is not None:
        index_value = (radon_index * 0.50) + (high_cc * 0.30) + (long_functions * 0.20)
    else:
        index_value = (high_cc * 0.55) + (long_functions * 0.45)

    return {
        "structural_index": _clamp_score(index_value),
        "method": "AST",
        "details": {
            "radon_available": bool(radon_signals.get("available")),
            "high_cyclomatic_functions": int(
                sum(int(r["metrics"].get("high_cyclomatic_functions", 0)) for r in file_reports)
            ),
            "long_functions": int(sum(int(r["metrics"].get("long_functions", 0)) for r in file_reports)),
            "max_cyclomatic_complexity": radon_signals.get("max_complexity"),
            "high_complexity_blocks": radon_signals.get("high_complexity_blocks"),
        },
    }


def _run_pydeps_cycle_count(repo_path: str) -> int:
    try:
        result = subprocess.run(
            ["pydeps", repo_path, "--show-cycles", "--no-dot"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=repo_path,
        )
        output = (result.stdout or "") + (result.stderr or "")
        cycles = len(re.findall(r"(?i)circular|cycle", output))
        if cycles == 0 and "Cycle" in output:
            cycles = output.count("Cycle")
        return cycles
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("pydeps cycle detection unavailable: %s", exc)
        return -1


def _write_import_linter_config(repo_path: str, root_package: str) -> str:
    config = f"""[importlinter]
root_package = {root_package}

[importlinter:contract:1]
name = No circular imports between modules
type = independence
modules =
    {root_package}
"""
    config_path = os.path.join(repo_path, ".importlinter")
    with open(config_path, "w", encoding="utf-8") as fh:
        fh.write(config)
    return config_path


def _detect_root_package(repo_path: str, python_files: list[dict]) -> str:
    parts: set[str] = set()
    for f in python_files:
        path = f.get("path", "").replace("\\", "/")
        if "/" in path:
            parts.add(path.split("/")[0])
    if parts:
        return sorted(parts)[0]
    for name in os.listdir(repo_path):
        init_path = os.path.join(repo_path, name, "__init__.py")
        if os.path.isfile(init_path):
            return name
    return "app"


def _run_import_linter_violations(repo_path: str, python_files: list[dict]) -> int:
    try:
        root = _detect_root_package(repo_path, python_files)
        _write_import_linter_config(repo_path, root)
        result = subprocess.run(
            ["lint-imports"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=repo_path,
        )
        if result.returncode == 0:
            return 0
        output = (result.stdout or "") + (result.stderr or "")
        matches = re.findall(r"(\d+)\s+violation", output, flags=re.IGNORECASE)
        if matches:
            return int(matches[0])
        return max(1, output.lower().count("broken contract"))
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("import-linter unavailable: %s", exc)
        return -1


def compute_circular_imports_signal(
    repo_path: str | None,
    python_files: list[dict],
    ast_circular_count: int,
) -> dict[str, Any]:
    """Tool signals for circular imports (aggregator computes final score)."""
    pydeps_cycles = _run_pydeps_cycle_count(repo_path) if repo_path else -1
    linter_violations = _run_import_linter_violations(repo_path, python_files) if repo_path else -1

    effective_cycles = ast_circular_count
    sources: list[str] = ["AST"]

    if pydeps_cycles >= 0:
        effective_cycles = max(effective_cycles, pydeps_cycles)
        sources.append("pydeps")
    if linter_violations >= 0:
        effective_cycles = max(effective_cycles, linter_violations)
        sources.append("import-linter")

    return {
        "method": METRIC_METHODS["circular_imports"],
        "cycle_count": effective_cycles,
        "details": {
            "ast_circular_count": ast_circular_count,
            "pydeps_cycles": pydeps_cycles if pydeps_cycles >= 0 else None,
            "import_linter_violations": linter_violations if linter_violations >= 0 else None,
            "effective_cycles": effective_cycles,
            "sources": sources,
        },
    }


def compute_static_architecture_metrics(
    file_reports: list[dict],
    aggregate_metrics: dict,
    repo_path: str | None,
    python_files: list[dict],
) -> dict[str, Any]:
    """Static analyzer output: signals + structural indices + tool signals only."""
    ast_circular = int(aggregate_metrics.get("circular_import_count", 0))
    radon_signals = _run_radon_signals(repo_path, python_files) if repo_path else {
        "available": False,
        "high_complexity_blocks": 0,
        "max_complexity": 0,
    }
    signals = _build_static_signals(file_reports, aggregate_metrics)
    return {
        "signals": signals,
        "structural_indices": {
            "module_decomposition": compute_module_decomposition_index(file_reports),
            "coupling": compute_coupling_index(file_reports, aggregate_metrics),
            "god_class_function": compute_god_class_index(file_reports, radon_signals),
        },
        "circular_imports_signal": compute_circular_imports_signal(
            repo_path, python_files, ast_circular
        ),
        "radon_signals": radon_signals,
    }


# ---------------------------------------------------------------------------
# Aggregator — sole scoring authority
# ---------------------------------------------------------------------------


def _llm_has_evidence(entry: dict[str, Any] | None) -> bool:
    if not entry:
        return False
    evidence = entry.get("evidence")
    if isinstance(evidence, list) and len(evidence) > 0:
        return True
    reason = str(entry.get("reason", "") or "").strip()
    return len(reason) > 12


def _derive_metric_constraints(
    metric_key: str,
    signals: dict[str, Any],
    structural_index: float | None = None,
) -> MetricConstraints:
    pattern_evidence = (signals.get("pattern_evidence") or {}).get(metric_key, True)
    cap1_global = bool(signals.get("cap1_severe_triad"))
    cap1_metric = cap1_global and metric_key in {
        "dependency_injection",
        "coupling",
        "repository_pattern",
        "swappable_components",
        "open_closed_readiness",
    }

    indirect = False
    if structural_index is not None and structural_index >= 55.0:
        indirect = True

    return MetricConstraints(
        cap_severe=cap1_metric,
        cap_absent_soft=not pattern_evidence,
        indirect_structural_evidence=indirect,
        structural_index=structural_index,
    )


def _reject_neutral_band(score: float, entry: dict[str, Any] | None) -> tuple[float, str]:
    reason = str((entry or {}).get("reason", "") or "")
    if NEUTRAL_SCORE_BAND[0] <= score <= NEUTRAL_SCORE_BAND[1] and not _llm_has_evidence(entry):
        return (
            SCORE_UNCERTAIN_DEFAULT,
            "Neutral 48-52 rejected; missing evidence defaults to 30. " + reason,
        )
    return score, reason


def _apply_constraints(
    candidate: float,
    constraints: MetricConstraints,
    entry: dict[str, Any] | None,
) -> tuple[float, str | None, list[str]]:
    """Apply caps as constraints on aggregator candidate — never replace with fixed score."""
    cap_applied: list[str] = []
    reason = str((entry or {}).get("reason", "") or "")

    if constraints.cap_severe:
        if candidate > CAP_SEVERE_MAX:
            candidate = CAP_SEVERE_MAX
            cap_applied.append(f"CAP1_SEVERE<={CAP_SEVERE_MAX:.0f}")

    if constraints.cap_absent_soft:
        ceiling = (
            CAP_ABSENT_INDIRECT_MAX
            if constraints.indirect_structural_evidence
            else CAP_ABSENT_SOFT_CEILING
        )
        if candidate > ceiling:
            candidate = ceiling
            cap_applied.append(
                f"CAP2_ABSENT<={ceiling:.0f}"
                + ("_indirect" if constraints.indirect_structural_evidence else "")
            )

    return candidate, ("; ".join(cap_applied) if cap_applied else None), cap_applied


def _extract_raw_llm_score(llm_data: dict | None, key: str) -> dict[str, Any] | None:
    if not llm_data or key not in llm_data:
        return None
    entry = llm_data.get(key)
    if not isinstance(entry, dict):
        return None
    raw = entry.get("score")
    if not isinstance(raw, (int, float)):
        return None
    return entry


def aggregate_metric_final(
    metric_key: str,
    llm_data: dict | None,
    static_bundle: dict[str, Any],
) -> dict[str, Any]:
    """Compute one final metric score (aggregator authority)."""
    signals = static_bundle.get("signals") or {}
    structural_indices = static_bundle.get("structural_indices") or {}

    if metric_key == "circular_imports":
        signal = static_bundle.get("circular_imports_signal") or {}
        cycle_count = int(signal.get("cycle_count", 0))
        score = _clamp_score(_normalize(cycle_count, 0.0, 5.0, reverse=True))
        return {
            "score": score,
            "method": METRIC_METHODS["circular_imports"],
            "details": signal.get("details", {}),
            "cap_applied": [],
            "aggregation": "tool_signal_only",
        }

    structural_index = None
    if metric_key in HYBRID_METRICS:
        struct_entry = structural_indices.get(metric_key) or {}
        structural_index = float(struct_entry.get("structural_index", 0.0))

    constraints = _derive_metric_constraints(metric_key, signals, structural_index)
    llm_entry = _extract_raw_llm_score(llm_data, metric_key)

    if llm_entry is None:
        if metric_key in HYBRID_METRICS and structural_index is not None:
            candidate = structural_index
            reason = "LLM raw score unavailable; aggregator uses structural index"
        else:
            candidate = SCORE_UNCERTAIN_DEFAULT
            reason = "LLM raw score unavailable; aggregator uncertain default=30"
        confidence = 0.0
        evidence: list = []
    else:
        candidate = float(llm_entry.get("score"))
        candidate, reason = _reject_neutral_band(candidate, llm_entry)
        confidence = round(max(0.0, min(1.0, float(llm_entry.get("confidence", 0.0) or 0.0))), 3)
        evidence = llm_entry.get("evidence") if isinstance(llm_entry.get("evidence"), list) else []

    if metric_key in HYBRID_METRICS and structural_index is not None:
        candidate = (structural_index * HYBRID_STRUCTURAL_WEIGHT) + (candidate * HYBRID_LLM_WEIGHT)
        aggregation = "hybrid_weighted"
        struct_entry = structural_indices.get(metric_key) or {}
        details = {
            **(struct_entry.get("details") or {}),
            "structural_index": structural_index,
            "llm_raw_score": float(llm_entry.get("score")) if llm_entry else None,
        }
    else:
        aggregation = "llm_raw"
        details = {}

    candidate, cap_label, cap_applied = _apply_constraints(candidate, constraints, llm_entry)
    if cap_label:
        reason = f"{cap_label}. {reason}".strip()

    return {
        "score": _clamp_score(candidate),
        "method": METRIC_METHODS[metric_key],
        "confidence": confidence,
        "reason": reason.strip(),
        "evidence": evidence,
        "details": details,
        "cap_applied": cap_applied,
        "aggregation": aggregation,
    }


def aggregate_architecture_score(
    static_metrics: dict[str, Any],
    llm_metrics: dict[str, Any] | None,
) -> dict[str, Any]:
    """Sole authority for final architecture scores."""
    metrics = {
        key: aggregate_metric_final(key, llm_metrics, static_metrics)
        for key in ARCHITECTURE_METRIC_KEYS
    }
    overall = sum(float(m.get("score", 0.0)) for m in metrics.values()) / len(metrics)
    return {
        "overall": _clamp_score(overall),
        "metrics": metrics,
        "metric_methods": METRIC_METHODS,
    }


# Backward-compatible aliases
compute_module_decomposition_ast = compute_module_decomposition_index
compute_coupling_ast = compute_coupling_index
compute_module_decomposition = compute_module_decomposition_index
compute_coupling = compute_coupling_index

# Legacy names used by tests — delegate to aggregator logic
def calibrate_llm_metric_entry(
    key: str,
    entry: dict[str, Any],
    severity_caps: dict[str, float],
) -> dict[str, Any]:
    """Deprecated: caps are applied only in aggregate_metric_final."""
    _ = severity_caps
    static_bundle = {"signals": {"pattern_evidence": {key: True}, "cap1_severe_triad": False}}
    if key in HYBRID_METRICS:
        static_bundle["structural_indices"] = {key: {"structural_index": 50.0, "details": {}}}
    merged_llm = {key: entry}
    result = aggregate_metric_final(key, merged_llm, static_bundle)
    return {**entry, "score": result["score"], "reason": result.get("reason", "")}


def _derive_severity_caps(signals: dict[str, Any]) -> dict[str, float]:
    """Deprecated compatibility shim."""
    caps: dict[str, float] = {}
    if signals.get("cap1_severe_triad"):
        for key in LLM_ONLY_METRICS | HYBRID_METRICS:
            caps[key] = CAP_SEVERE_MAX
    return caps

