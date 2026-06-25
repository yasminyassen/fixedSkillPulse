"""Tests for deterministic requirement coverage scoring."""

from ai_services.requirements.coverage.scoring import (
    ac_score_from_status,
    overall_coverage_score,
    story_coverage_score,
    story_coverage_status,
)


def test_ac_scores():
    assert ac_score_from_status("COVERED") == 1.0
    assert ac_score_from_status("PARTIALLY_COVERED") == 0.5
    assert ac_score_from_status("NOT_COVERED") == 0.0


def test_story_coverage_average():
    assert story_coverage_score(["COVERED", "COVERED"]) == 1.0
    assert story_coverage_score(["COVERED", "NOT_COVERED"]) == 0.5
    assert story_coverage_score(["PARTIALLY_COVERED"]) == 0.5
    assert story_coverage_score([]) == 0.0


def test_story_status_all_acs_covered():
    statuses = ["COVERED", "COVERED", "COVERED"]
    assert story_coverage_score(statuses) == 1.0
    assert story_coverage_status(story_coverage_score(statuses), statuses) == "implemented"


def test_story_status_high_average_with_one_missing_ac_is_partial():
    statuses = ["COVERED", "COVERED", "COVERED", "COVERED", "COVERED", "COVERED", "COVERED", "NOT_COVERED"]
    assert story_coverage_score(statuses) >= 0.85
    assert story_coverage_status(story_coverage_score(statuses), statuses) == "partially_implemented"


def test_story_status_mixture_of_covered_and_partial_is_partial():
    statuses = ["COVERED", "PARTIALLY_COVERED", "COVERED"]
    assert story_coverage_status(story_coverage_score(statuses), statuses) == "partially_implemented"


def test_story_status_all_not_covered_is_not_implemented():
    statuses = ["NOT_COVERED", "NOT_COVERED"]
    assert story_coverage_score(statuses) == 0.0
    assert story_coverage_status(story_coverage_score(statuses), statuses) == "not_implemented"


def test_story_status_critical_ac_partially_covered_is_partial():
    statuses = ["COVERED", "COVERED", "COVERED", "COVERED", "PARTIALLY_COVERED"]
    assert story_coverage_score(statuses) >= 0.85
    assert story_coverage_status(story_coverage_score(statuses), statuses) == "partially_implemented"


def test_story_status_critical_ac_not_covered_is_partial_when_other_work_exists():
    statuses = ["COVERED", "COVERED", "NOT_COVERED"]
    assert story_coverage_status(story_coverage_score(statuses), statuses) == "partially_implemented"


def test_story_status_low_score_with_no_covered_or_partial_is_not_implemented():
    assert story_coverage_status(0.24, ["NOT_COVERED"]) == "not_implemented"


def test_overall_weighted_coverage():
    stories = [
        (1.0, "critical"),
        (0.5, "high"),
        (0.0, "low"),
    ]
    # (1.0*1.0 + 0.5*0.8 + 0.0*0.4) / (1.0+0.8+0.4) = 1.4/2.2
    assert overall_coverage_score(stories) == round(1.4 / 2.2, 4)
