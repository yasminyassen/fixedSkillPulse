from typing import Dict, Any
import time


def build_unified_schema(ast_result: Dict[str, Any], llm_result: Dict[str, Any], commit_sha: str | None = None) -> Dict[str, Any]:
    """Combine AST and LLM outputs into the unified metric schema.

    Returns a mapping of required keys to evidence entries.
    """
    ts = int(time.time())
    unified: Dict[str, Any] = {"generated_at": ts, "commit": commit_sha, "metrics": {}}

    # Helper to attach an entry
    def attach(name, value, source, confidence, ref=None):
        unified["metrics"].setdefault(name, [])
        unified["metrics"][name].append({
            "value": value,
            "source": source,
            "confidence": confidence,
            "ref": ref,
        })

    # AST hints
    ast_agg = ast_result.get("aggregate_metrics", {})
    files = ast_result.get("files", [])

    # code_smells (AST: long functions, style violations)
    attach("code_smells", ast_agg.get("long_functions", 0), "AST", 0.6)
    attach("duplication", ast_agg.get("avg_duplication_score", 0.0), "AST", 0.5)
    attach("complexity", ast_agg.get("avg_cyclomatic_complexity", 0.0), "AST", 0.7)
    attach("documentation_coverage", ast_agg.get("avg_docstring_coverage", 1.0), "AST", 0.7)
    attach("test_indicators", ast_agg.get("avg_test_function_ratio", 0.0), "AST", 0.6)
    attach("import_coupling", ast_agg.get("import_coupling_total", 0), "AST", 0.6)
    attach("efferent_coupling", ast_agg.get("efferent_coupling_total", 0), "AST", 0.6)
    attach("circular_imports", ast_agg.get("circular_import_count", 0), "AST", 0.8)

    arch = ast_result.get("architecture_metrics", {})
    if isinstance(arch, dict):
        for metric_key, metric_entry in (arch.get("metrics") or {}).items():
            if isinstance(metric_entry, dict):
                attach(
                    f"arch_{metric_key}",
                    metric_entry.get("score"),
                    metric_entry.get("method", "unknown"),
                    metric_entry.get("confidence", 0.5),
                )

    # LLM problem solving components
    if llm_result:
        for comp in ("algorithms", "data_structures", "balanced_complexity", "edge_cases"):
            entry = llm_result.get(comp)
            if entry:
                attach(comp, entry.get("score"), "LLM", entry.get("confidence", 0.5), ref=entry.get("evidence"))

    return unified
