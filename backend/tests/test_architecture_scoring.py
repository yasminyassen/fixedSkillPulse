from app.services.architecture_scoring import (
    CAP_SEVERE_MAX,
    CAP_ABSENT_SOFT_CEILING,
    METRIC_METHODS,
    SCORE_UNCERTAIN_DEFAULT,
    aggregate_architecture_score,
    aggregate_metric_final,
    calibrate_llm_metric_entry,
    compute_coupling_index,
    compute_module_decomposition_index,
    compute_static_architecture_metrics,
    _derive_metric_constraints,
)
from app.services.code_intelligence import analyze_python_files
from tests.fixtures.candidate_samples import GOOD_API, POOR_API as BAD_API


def _file_reports(content: str) -> list[dict]:
    return analyze_python_files([
        {"path": "app/main.py", "filename": "main.py", "content": content}
    ])["files"]


def test_architecture_metric_methods_cover_all_ten() -> None:
    assert len(METRIC_METHODS) == 10
    assert METRIC_METHODS["cohesion"] == "LLM"
    assert METRIC_METHODS["circular_imports"] == "pydeps + import-linter"
    assert METRIC_METHODS["god_class_function"] == "LLM + AST (radon)"


def test_static_outputs_signals_not_final_scores() -> None:
    reports = _file_reports(GOOD_API)
    agg = analyze_python_files([{"path": "app/main.py", "content": GOOD_API}])["aggregate_metrics"]
    static = compute_static_architecture_metrics(reports, agg, None, [])
    assert "signals" in static
    assert "structural_indices" in static
    assert "circular_imports_signal" in static
    decomp = static["structural_indices"]["module_decomposition"]
    assert "structural_index" in decomp
    assert "score" not in decomp


def _mock_llm(score: float) -> dict:
    return {
        key: {
            "score": score,
            "confidence": 0.8,
            "reason": f"Mock evaluation at {score}",
            "evidence": ["explicit structural evidence"],
        }
        for key in (
            "layer_count_srp",
            "repository_pattern",
            "dependency_injection",
            "open_closed_readiness",
            "swappable_components",
            "cohesion",
            "coupling",
            "module_decomposition",
            "god_class_function",
        )
    }


def test_static_architecture_metrics_score_good_higher_than_bad() -> None:
    good_reports = _file_reports(GOOD_API)
    bad_reports = _file_reports(BAD_API)
    good_agg = analyze_python_files([{"path": "app/main.py", "content": GOOD_API}])["aggregate_metrics"]
    bad_agg = analyze_python_files([{"path": "app/main.py", "content": BAD_API}])["aggregate_metrics"]

    good_static = compute_static_architecture_metrics(good_reports, good_agg, None, [])
    bad_static = compute_static_architecture_metrics(bad_reports, bad_agg, None, [])

    good_result = aggregate_architecture_score(good_static, _mock_llm(78.0))
    bad_result = aggregate_architecture_score(bad_static, _mock_llm(32.0))

    assert good_result["overall"] >= bad_result["overall"]
    assert len(good_result["metrics"]) == 10


def test_module_decomposition_index_returns_structural_index() -> None:
    reports = _file_reports(GOOD_API)
    decomp = compute_module_decomposition_index(reports)
    assert 0 <= decomp["structural_index"] <= 100
    assert decomp["method"] == "AST"
    assert "total_classes" in decomp["details"]


def test_coupling_index_uses_business_inline_signals() -> None:
    reports = _file_reports(GOOD_API)
    agg = analyze_python_files([{"path": "app/main.py", "content": GOOD_API}])["aggregate_metrics"]
    coupling = compute_coupling_index(reports, agg)
    assert coupling["method"] == "AST"
    assert "inline_concrete_instantiations_business" in coupling["details"]


def test_aggregator_rejects_neutral_fifty() -> None:
    static = {
        "signals": {
            "pattern_evidence": {"cohesion": True},
            "cap1_severe_triad": False,
        },
        "structural_indices": {},
    }
    llm = {
        "cohesion": {
            "score": 50.0,
            "confidence": 0.9,
            "reason": "unclear",
            "evidence": [],
        }
    }
    result = aggregate_metric_final("cohesion", llm, static)
    assert result["score"] == SCORE_UNCERTAIN_DEFAULT


def test_cap1_only_when_all_three_triad_conditions() -> None:
    signals_partial = {
        "cap1_severe_triad": False,
        "pattern_evidence": {"dependency_injection": False},
    }
    constraints = _derive_metric_constraints("dependency_injection", signals_partial, None)
    assert constraints.cap_severe is False
    assert constraints.cap_absent_soft is True

    signals_full = {
        "cap1_severe_triad": True,
        "pattern_evidence": {"dependency_injection": False},
    }
    constraints_severe = _derive_metric_constraints("dependency_injection", signals_full, None)
    assert constraints_severe.cap_severe is True


def test_cap1_applied_only_in_aggregator() -> None:
    static = {
        "signals": {
            "cap1_severe_triad": True,
            "pattern_evidence": {"dependency_injection": False},
        },
        "structural_indices": {},
    }
    llm = {
        "dependency_injection": {
            "score": 75.0,
            "confidence": 0.8,
            "reason": "constructor injection present",
            "evidence": ["UserService injected via __init__"],
        }
    }
    result = aggregate_metric_final("dependency_injection", llm, static)
    assert result["score"] <= CAP_SEVERE_MAX
    assert "CAP1_SEVERE" in "".join(result.get("cap_applied", []))


def test_llm_unavailable_defaults_to_30_or_cap_in_aggregator() -> None:
    reports = _file_reports(GOOD_API)
    agg = analyze_python_files([{"path": "app/main.py", "content": GOOD_API}])["aggregate_metrics"]
    static = compute_static_architecture_metrics(reports, agg, None, [])
    result = aggregate_architecture_score(static, None)
    for key in ("layer_count_srp", "repository_pattern", "cohesion"):
        score = result["metrics"][key]["score"]
        assert score == SCORE_UNCERTAIN_DEFAULT or score <= CAP_SEVERE_MAX


def test_cap2_soft_ceiling_with_zero_evidence() -> None:
    static = {
        "signals": {
            "cap1_severe_triad": False,
            "pattern_evidence": {"repository_pattern": False},
        },
        "structural_indices": {},
    }
    llm = {
        "repository_pattern": {
            "score": 80.0,
            "confidence": 0.9,
            "reason": "no repository found",
            "evidence": ["raw SQL in handlers"],
        }
    }
    result = aggregate_metric_final("repository_pattern", llm, static)
    assert result["score"] <= CAP_ABSENT_SOFT_CEILING


def test_llm_layer_does_not_assign_final_via_legacy_shim() -> None:
    entry = {"score": 50.0, "confidence": 0.4, "reason": "unclear", "evidence": []}
    result = calibrate_llm_metric_entry("cohesion", entry, {})
    assert result["score"] == SCORE_UNCERTAIN_DEFAULT
