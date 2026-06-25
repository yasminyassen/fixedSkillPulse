import asyncio
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("sendgrid_api_key", "test-sendgrid")
os.environ.setdefault("from_email", "test@example.com")

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.analysis import get_sonar_results
from app.db.database import Base
from app.db.models import (
    AnalysisRun,
    Repository,
    SkillScore,
    SonarAnalysisSummary,
    SonarFileMeasure,
    SonarIssue,
    User,
)


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
            SonarFileMeasure.__table__,
            SonarIssue.__table__,
        ],
    )
    return sessionmaker(bind=engine)()


def _user(db, user_id: int = 1) -> User:
    user = User(
        id=user_id,
        github_id=f"gh-{user_id}",
        username=f"user{user_id}",
        full_name=f"User {user_id}",
        work_email=f"user{user_id}@example.com",
        hashed_password="hashed",
    )
    db.add(user)
    return user


def _run(db, user_id: int = 1) -> AnalysisRun:
    repo = Repository(
        github_repo_id="repo-1",
        name="repo",
        full_name="acme/repo",
        url="https://example.test/acme/repo",
    )
    db.add(repo)
    db.flush()
    run = AnalysisRun(
        repository_id=repo.id,
        user_id=user_id,
        branch="main",
        analysis_scope="contribution",
        status="completed",
    )
    db.add(run)
    db.flush()
    return run


def test_get_sonar_results_returns_frontend_safe_payload():
    db = _db_session()
    try:
        user = _user(db)
        run = _run(db, user.id)
        db.add(SkillScore(
            analysis_run_id=run.id,
            user_id=user.id,
            overall_score=84.25,
            sonar_health_score=87.5,
            security_awareness_score=76.67,
        ))
        db.add(SonarAnalysisSummary(
            analysis_run_id=run.id,
            user_id=user.id,
            project_key="skill-pulse:acme_repo:main",
            quality_gate="OK",
            sonar_health_score=87.5,
            measures={"bugs": "0", "code_smells": "4", "coverage": "72.5"},
            coverage={"status": "ready"},
            raw_payload={"internal": True},
        ))
        db.add(SonarFileMeasure(
            analysis_run_id=run.id,
            user_id=user.id,
            file_path="app/services/auth.py",
            measures={"coverage": "80", "ncloc": "120"},
            coverage=80,
            duplicated_lines=0,
            duplicated_lines_density=0,
            ncloc=120,
            complexity=8,
            cognitive_complexity=5,
            functions=6,
            classes=1,
            statements=90,
        ))
        db.add(SonarIssue(
            analysis_run_id=run.id,
            user_id=user.id,
            issue_key="ISSUE-1",
            file_path="app/services/auth.py",
            line=42,
            type="CODE_SMELL",
            severity="MAJOR",
            rule="python:S3776",
            message="Refactor this function.",
            status="OPEN",
            raw_issue={"hidden": True},
        ))
        db.add(SonarIssue(
            analysis_run_id=run.id,
            user_id=user.id,
            issue_key="ISSUE-CLOSED",
            file_path="app/services/auth.py",
            line=43,
            type="CODE_SMELL",
            severity="MAJOR",
            rule="python:S3776",
            message="Already fixed.",
            status="CLOSED",
            raw_issue={"hidden": True},
        ))
        db.commit()

        payload = asyncio.run(get_sonar_results(run.id, False, db, user))

        assert payload["analysis_run_id"] == run.id
        assert payload["repo"] == "acme/repo"
        assert payload["skill_score"] == 84.25
        assert payload["skill_score_level"] == "Very Good"
        assert payload["sonar"]["available"] is True
        assert payload["sonar"]["measures"] == {"bugs": 0, "code_smells": 4, "coverage": 72.5}
        assert "raw_payload" not in payload["sonar"]
        assert payload["files"][0]["file_path"] == "app/services/auth.py"
        assert payload["files"][0]["measures"] == {"coverage": 80, "ncloc": 120}
        assert payload["files"][0]["complexity"] == 8
        assert payload["files"][0]["cognitive_complexity"] == 5
        assert payload["files"][0]["functions"] == 6
        assert payload["issues"][0]["issue_key"] == "ISSUE-1"
        assert [issue["issue_key"] for issue in payload["issues"]] == ["ISSUE-1"]
        assert "raw_issue" not in payload["issues"][0]
        assert payload["summary"] == {
            "files_count": 1,
            "issues_count": 1,
            "bugs_count": 0,
            "code_smells_count": 1,
        }
    finally:
        db.close()


def test_get_sonar_results_returns_available_false_without_sonar_rows():
    db = _db_session()
    try:
        user = _user(db)
        run = _run(db, user.id)
        db.add(SkillScore(analysis_run_id=run.id, user_id=user.id))
        db.commit()

        payload = asyncio.run(get_sonar_results(run.id, False, db, user))

        assert payload["sonar"] == {
            "available": False,
            "reason": "sonar_results_not_found",
        }
        assert payload["files"] == []
        assert payload["issues"] == []
        assert payload["summary"]["issues_count"] == 0
    finally:
        db.close()


def test_get_sonar_results_returns_404_for_inaccessible_run():
    db = _db_session()
    try:
        owner = _user(db, 1)
        outsider = _user(db, 2)
        run = _run(db, owner.id)
        db.commit()

        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_sonar_results(run.id, False, db, outsider))

        assert exc.value.status_code == 404
    finally:
        db.close()
