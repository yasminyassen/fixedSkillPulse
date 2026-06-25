from app.services.code_intelligence import analyze_python_files
from tests.fixtures.candidate_samples import GOOD_API, POOR_API as BAD_API


def _analyze(content: str) -> dict:
    return analyze_python_files([
        {"path": "app/main.py", "filename": "main.py", "content": content}
    ])


def test_static_scoring_separates_good_and_bad_candidate_code() -> None:
    good = _analyze(GOOD_API)
    bad = _analyze(BAD_API)

    good_scores = good["scores"]
    bad_scores = bad["scores"]

    assert good_scores["code_quality"] > bad_scores["code_quality"]
    assert good_scores["maintainability"] > bad_scores["maintainability"]
    assert all(score <= 100 for score in good_scores.values() if isinstance(score, (int, float)))


def test_bad_patterns_are_detected_in_metrics() -> None:
    good_metrics = _analyze(GOOD_API)["aggregate_metrics"]
    bad_metrics = _analyze(BAD_API)["aggregate_metrics"]

    assert good_metrics["avg_type_annotation_coverage"] > bad_metrics["avg_type_annotation_coverage"]
    assert bad_metrics["weak_type_hints"] >= good_metrics["weak_type_hints"]
    assert bad_metrics["dangerous_patterns"] > good_metrics["dangerous_patterns"]
    assert bad_metrics["error_dict_returns"] > good_metrics["error_dict_returns"]
    assert good_metrics["explicit_raises"] > bad_metrics["explicit_raises"]
