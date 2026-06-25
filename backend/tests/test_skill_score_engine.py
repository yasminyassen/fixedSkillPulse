import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app.services.sonarqube_score_service import (
    classify_skill_score,
    compute_skill_score_engine,
)


def test_compute_skill_score_engine_combines_sonar_and_security_scores():
    assert compute_skill_score_engine(sonar_health_score=80, security_score=90) == 83.0
    assert compute_skill_score_engine(sonar_health_score=87.5, security_score=76.25) == 84.12
    assert compute_skill_score_engine(sonar_health_score=None, security_score=90) is None
    assert compute_skill_score_engine(sonar_health_score=90, security_score=None) is None


def test_classify_skill_score_boundaries():
    assert classify_skill_score(100) == "Excellent"
    assert classify_skill_score(90) == "Excellent"
    assert classify_skill_score(89) == "Very Good"
    assert classify_skill_score(80) == "Very Good"
    assert classify_skill_score(79) == "Good"
    assert classify_skill_score(70) == "Good"
    assert classify_skill_score(69) == "Fair"
    assert classify_skill_score(60) == "Fair"
    assert classify_skill_score(59) == "Needs Improvement"
    assert classify_skill_score(None) == "Unavailable"
