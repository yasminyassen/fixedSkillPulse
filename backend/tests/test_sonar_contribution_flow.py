import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import (
    AnalysisRun,
    Repository,
    SecurityFinding,
    SonarAnalysisSummary,
    SonarFileMeasure,
    SonarIssue,
    User,
)
from app.services.analysis_orchestrator import (
    _existing_python_contribution_files,
    _persist_sonar_results,
)
from app.services import sonarqube_service
from app.services.sonarqube_service import write_sonar_properties


def _measure(metric, value):
    return {"metric": metric, "value": value}


def test_write_sonar_properties_adds_normalized_python_inclusions(tmp_path, monkeypatch):
    monkeypatch.delenv("SONAR_TOKEN", raising=False)

    write_sonar_properties(
        repo_path=str(tmp_path),
        project_key="skill-pulse:repo:main",
        included_files=[
            r"\app\api\users.py",
            "app/services/auth.py",
            "app/services/auth.py",
            "frontend/src/App.tsx",
            "",
        ],
    )

    content = (tmp_path / "sonar-project.properties").read_text(encoding="utf-8")

    assert "sonar.sources=." in content
    assert "sonar.inclusions=app/api/users.py,app/services/auth.py" in content
    assert "frontend/src/App.tsx" not in content


def test_existing_python_contribution_files_filters_to_existing_repo_python_files(tmp_path):
    repo_root = tmp_path
    (repo_root / "app" / "api").mkdir(parents=True)
    (repo_root / "app" / "api" / "users.py").write_text("print('ok')", encoding="utf-8")
    (repo_root / "app" / "api" / "users.ts").write_text("console.log('no')", encoding="utf-8")

    result = _existing_python_contribution_files(
        str(repo_root),
        [
            r"app\api\users.py",
            "app/api/users.py",
            "app/api/missing.py",
            "app/api/users.ts",
            "../outside.py",
        ],
    )

    assert result == ["app/api/users.py"]


def test_get_file_measures_falls_back_and_filters_file_components(monkeypatch):
    monkeypatch.setattr(sonarqube_service, "get_supported_metrics", lambda metrics: metrics)
    calls = []

    def fake_get_json(path, params=None):
        calls.append((path, dict(params or {})))
        if params and params.get("qualifiers") == "FIL":
            return {"components": [], "paging": {"total": 0}}
        return {
            "components": [
                {
                    "key": "skill-pulse:repo:main:app/services/auth.py",
                    "qualifier": "FIL",
                    "path": "app/services/auth.py",
                    "measures": [_measure("complexity", "8")],
                },
                {
                    "key": "skill-pulse:repo:main:app/services",
                    "qualifier": "DIR",
                    "path": "app/services",
                    "measures": [_measure("complexity", "8")],
                },
            ],
            "paging": {"total": 2},
        }

    monkeypatch.setattr(sonarqube_service, "_get_json", fake_get_json)

    payload = sonarqube_service.get_file_measures("skill-pulse:repo:main")

    assert calls[0][1]["qualifiers"] == "FIL"
    assert "qualifiers" not in calls[1][1]
    assert [component["path"] for component in payload["components"]] == ["app/services/auth.py"]


def test_persist_sonar_results_populates_sonar_tables_without_security_findings():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[
            User.__table__,
            Repository.__table__,
            AnalysisRun.__table__,
            SecurityFinding.__table__,
            SonarAnalysisSummary.__table__,
            SonarFileMeasure.__table__,
            SonarIssue.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        repo = Repository(github_repo_id="1", name="repo", full_name="acme/repo", url="https://example.test/repo")
        db.add(repo)
        db.flush()
        run = AnalysisRun(repository_id=repo.id, user_id=None, branch="main", status="running")
        db.add(run)
        db.flush()

        sonar_result = {
            "project_key": "skill-pulse:acme_repo:main",
            "sonar": {
                "coverage": {"status": "ready"},
                "scanner": {"stdout": "ok"},
                "ce_task": {"task": {"status": "SUCCESS"}},
                "quality_gate": {"projectStatus": {"status": "OK"}},
                "measures": {
                    "component": {
                        "measures": [
                            _measure("bugs", "1"),
                            _measure("code_smells", "2"),
                        ]
                    }
                },
                "file_measures": {
                    "components": [
                        {
                            "key": "skill-pulse:acme_repo:main:app/api/users.py",
                            "measures": [
                                _measure("coverage", "91.2"),
                                _measure("duplicated_lines", "4"),
                                _measure("duplicated_lines_density", "1.5"),
                                _measure("ncloc", "120"),
                                _measure("complexity", "12"),
                                _measure("cognitive_complexity", "9"),
                                _measure("functions", "8"),
                                _measure("classes", "2"),
                                _measure("statements", "80"),
                            ],
                        }
                    ]
                },
                "issues": {
                    "issues": [
                        {
                            "key": "ISSUE-1",
                            "component": "skill-pulse:acme_repo:main:app/api/users.py",
                            "line": 12,
                            "type": "BUG",
                            "severity": "MAJOR",
                            "rule": "python:S1",
                            "message": "Fix this bug.",
                            "status": "OPEN",
                        },
                        {
                            "key": "ISSUE-CLOSED",
                            "component": "skill-pulse:acme_repo:main:app/api/users.py",
                            "line": 13,
                            "type": "CODE_SMELL",
                            "severity": "MAJOR",
                            "rule": "python:S2",
                            "message": "Already fixed.",
                            "status": "CLOSED",
                        }
                    ]
                },
            },
        }

        _persist_sonar_results(db, run, None, sonar_result, 88.5)
        db.commit()

        summary = db.query(SonarAnalysisSummary).one()
        file_measure = db.query(SonarFileMeasure).one()
        issue = db.query(SonarIssue).one()

        assert summary.project_key == "skill-pulse:acme_repo:main"
        assert summary.quality_gate == "OK"
        assert summary.sonar_health_score == 88.5
        assert summary.measures == {"bugs": "1", "code_smells": "2"}
        assert file_measure.file_path == "app/api/users.py"
        assert file_measure.coverage == 91.2
        assert file_measure.duplicated_lines_density == 1.5
        assert issue.issue_key == "ISSUE-1"
        assert issue.file_path == "app/api/users.py"
        assert db.query(SecurityFinding).count() == 0
    finally:
        db.close()
