import os
from datetime import datetime, timezone

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.manager_dashboard import (
    _normalise_overview_recommendations,
    _repository_manager_recommendation_payload,
    _risk_groups,
)
from app.db.database import Base
from app.db.models import (
    AnalysisRun,
    ContributorAnalysisSummary,
    Repository,
    SecurityFinding,
    SkillScore,
    SonarAnalysisSummary,
    SonarFileMeasure,
    SonarIssue,
    User,
    UserRole,
)
from app.schemas.manager_schemas import ManagerDashboardRiskGroups


def _db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[
            User.__table__,
            Repository.__table__,
            AnalysisRun.__table__,
            SkillScore.__table__,
            SonarAnalysisSummary.__table__,
            ContributorAnalysisSummary.__table__,
            SonarFileMeasure.__table__,
            SonarIssue.__table__,
            SecurityFinding.__table__,
        ],
    )
    return sessionmaker(bind=engine)()


def _user(db, user_id: int, role: UserRole) -> User:
    user = User(
        id=user_id,
        github_id=f"gh-{user_id}",
        username=f"user{user_id}",
        full_name=f"User {user_id}",
        work_email=f"user{user_id}@example.com",
        hashed_password="hashed",
        role=role,
    )
    db.add(user)
    return user


def test_overview_recommendations_do_not_fall_back_to_legacy_buckets():
    recommendations = _normalise_overview_recommendations(
        {
            "actionable_recommendations": {
                "mandatory": ["legacy mandatory text"],
                "highly_required": ["legacy required text"],
            },
            "fix_first": ["repo-specific fix"],
        }
    )

    assert recommendations.fix_first == ["repo-specific fix"]
    assert recommendations.prioritize_next == []
    assert recommendations.actionable_recommendations == ["repo-specific fix"]


def test_repository_recommendation_payload_uses_selected_run_and_repo_only():
    db = _db_session()
    try:
        manager = _user(db, 1, UserRole.manager)
        developer_one = _user(db, 2, UserRole.developer)
        developer_two = _user(db, 3, UserRole.developer)
        repo_one = Repository(
            github_repo_id="repo-1",
            name="repo-one",
            full_name="acme/repo-one",
            url="https://example.test/acme/repo-one",
        )
        repo_two = Repository(
            github_repo_id="repo-2",
            name="repo-two",
            full_name="acme/repo-two",
            url="https://example.test/acme/repo-two",
        )
        db.add_all([repo_one, repo_two])
        db.flush()

        selected_run = AnalysisRun(
            repository_id=repo_one.id,
            user_id=manager.id,
            branch="main",
            analysis_scope="repository",
            status="completed",
            completed_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
        )
        other_run = AnalysisRun(
            repository_id=repo_two.id,
            user_id=manager.id,
            branch="main",
            analysis_scope="repository",
            status="completed",
            completed_at=datetime(2026, 6, 21, tzinfo=timezone.utc),
        )
        db.add_all([selected_run, other_run])
        db.flush()

        db.add_all(
            [
                SkillScore(
                    analysis_run_id=selected_run.id,
                    user_id=manager.id,
                    overall_score=71,
                    sonar_health_score=62,
                    security_awareness_score=80,
                ),
                SonarAnalysisSummary(
                    analysis_run_id=selected_run.id,
                    user_id=manager.id,
                    quality_gate="ERROR",
                    sonar_health_score=62,
                    measures={
                        "coverage": 38,
                        "bugs": 4,
                        "code_smells": 21,
                        "duplicated_lines_density": 9,
                        "complexity": 44,
                        "cognitive_complexity": 57,
                    },
                ),
                SonarFileMeasure(
                    analysis_run_id=selected_run.id,
                    file_path="src/risky.py",
                    coverage=12,
                    duplicated_lines_density=18,
                    complexity=30,
                    cognitive_complexity=42,
                ),
                SonarFileMeasure(
                    analysis_run_id=other_run.id,
                    file_path="src/other-repo.py",
                    coverage=0,
                    complexity=99,
                    cognitive_complexity=99,
                ),
                SonarIssue(
                    analysis_run_id=selected_run.id,
                    file_path="src/risky.py",
                    type="BUG",
                    severity="HIGH",
                    rule="python:S1",
                    message="Selected repo issue",
                ),
                SonarIssue(
                    analysis_run_id=other_run.id,
                    file_path="src/other-repo.py",
                    type="BUG",
                    severity="HIGH",
                    message="Other repo issue",
                ),
                SecurityFinding(
                    analysis_run_id=selected_run.id,
                    file_path="src/risky.py",
                    severity="HIGH",
                    rule="B1",
                    description="Selected repo finding",
                ),
                SecurityFinding(
                    analysis_run_id=other_run.id,
                    file_path="src/other-repo.py",
                    severity="HIGH",
                    description="Other repo finding",
                ),
                ContributorAnalysisSummary(
                    analysis_run_id=selected_run.id,
                    repository_id=repo_one.id,
                    user_id=developer_one.id,
                    skill_score=70,
                    coverage=38,
                ),
                ContributorAnalysisSummary(
                    analysis_run_id=other_run.id,
                    repository_id=repo_two.id,
                    user_id=developer_two.id,
                    skill_score=10,
                    coverage=0,
                ),
            ]
        )
        db.commit()

        contributor_rows = (
            db.query(ContributorAnalysisSummary, AnalysisRun, Repository, User)
            .join(AnalysisRun, ContributorAnalysisSummary.analysis_run_id == AnalysisRun.id)
            .join(Repository, ContributorAnalysisSummary.repository_id == Repository.id)
            .join(User, ContributorAnalysisSummary.user_id == User.id)
            .all()
        )

        payload = _repository_manager_recommendation_payload(
            db,
            selected_run,
            manager.id,
            contributor_rows,
            ManagerDashboardRiskGroups(),
        )

        assert payload["repository"]["id"] == repo_one.id
        assert payload["repository"]["latest_analysis_run_id"] == selected_run.id
        assert payload["scores"]["coverage"] == 38
        assert [item["file_path"] for item in payload["top_risky_files"]] == ["src/risky.py"]
        assert [item["message"] for item in payload["top_sonar_issues"]] == ["Selected repo issue"]
        assert [item["description"] for item in payload["top_security_findings"]] == ["Selected repo finding"]
        assert [item["repository_id"] for item in payload["contributors"]] == [repo_one.id]
    finally:
        db.close()


def test_manager_dashboard_risks_return_only_code_smells_and_bug_files():
    db = _db_session()
    try:
        manager = _user(db, 1, UserRole.manager)
        repo = Repository(
            github_repo_id="repo-risks",
            name="repo-risks",
            full_name="acme/repo-risks",
            url="https://example.test/acme/repo-risks",
        )
        db.add(repo)
        db.flush()

        run = AnalysisRun(
            repository_id=repo.id,
            user_id=manager.id,
            branch="main",
            analysis_scope="repository",
            status="completed",
            completed_at=datetime(2026, 6, 22, tzinfo=timezone.utc),
        )
        db.add(run)
        db.flush()

        db.add_all(
            [
                SonarIssue(
                    analysis_run_id=run.id,
                    file_path="src/smelly.py",
                    type="CODE_SMELL",
                    severity="MAJOR",
                    message="Smell one",
                ),
                SonarIssue(
                    analysis_run_id=run.id,
                    file_path="src/smelly.py",
                    type="CODE_SMELL",
                    severity="MINOR",
                    message="Smell two",
                ),
                SonarIssue(
                    analysis_run_id=run.id,
                    file_path="src/buggy.py",
                    type="BUG",
                    severity="CRITICAL",
                    message="Bug one",
                ),
                SonarFileMeasure(
                    analysis_run_id=run.id,
                    file_path="src/complex.py",
                    coverage=10,
                    complexity=99,
                    cognitive_complexity=99,
                ),
                SecurityFinding(
                    analysis_run_id=run.id,
                    file_path="src/security.py",
                    severity="HIGH",
                    description="Security finding",
                ),
            ]
        )
        db.commit()

        risks = _risk_groups(db, run)
        payload = risks.model_dump() if hasattr(risks, "model_dump") else risks.dict()

        assert set(payload.keys()) == {"high_code_smells", "high_bug_files"}
        assert payload["high_code_smells"][0]["title"] == "smelly.py"
        assert payload["high_code_smells"][0]["count"] == 2
        assert payload["high_code_smells"][0]["severity"] == "Medium"
        assert payload["high_bug_files"][0]["title"] == "buggy.py"
        assert payload["high_bug_files"][0]["count"] == 1
        assert payload["high_bug_files"][0]["severity"] == "Low"
    finally:
        db.close()
