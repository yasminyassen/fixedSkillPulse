from app.services.code_intelligence import analyze_python_files
from tests.fixtures.candidate_samples import CANDIDATE_LEVELS, GOOD_API, POOR_API


def _score(level: str) -> dict:
    result = analyze_python_files([
        {
            "path": f"app/{level}.py",
            "filename": f"{level}.py",
            "content": CANDIDATE_LEVELS[level],
        }
    ])
    return result["scores"]


def test_candidate_levels_rank_from_excellent_to_poor() -> None:
    scores = {level: _score(level) for level in CANDIDATE_LEVELS}

    assert scores["excellent"]["code_quality"] >= scores["good"]["code_quality"]
    assert scores["excellent"]["architecture"] > scores["good"]["architecture"]
    assert scores["good"]["code_quality"] > scores["average"]["code_quality"]
    assert scores["average"]["code_quality"] > scores["weak"]["code_quality"]
    assert scores["weak"]["code_quality"] > scores["poor"]["code_quality"]

    assert scores["average"]["architecture"] > scores["poor"]["architecture"]
    assert scores["weak"]["architecture"] > scores["poor"]["architecture"]
    assert scores["weak"]["maintainability"] > scores["poor"]["maintainability"]
    assert scores["good"]["maintainability"] > scores["poor"]["maintainability"]
    assert scores["good"]["architecture"] > scores["poor"]["architecture"]

    for level_scores in scores.values():
        for value in level_scores.values():
            if isinstance(value, (int, float)):
                assert value <= 100


def test_good_beats_poor_on_core_signals() -> None:
    good = analyze_python_files([{"path": "app/main.py", "content": GOOD_API}])
    poor = analyze_python_files([{"path": "app/main.py", "content": POOR_API}])

    assert good["scores"]["code_quality"] > poor["scores"]["code_quality"]
    assert poor["aggregate_metrics"]["dangerous_patterns"] > good["aggregate_metrics"]["dangerous_patterns"]
