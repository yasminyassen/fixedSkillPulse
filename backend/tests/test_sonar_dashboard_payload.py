import os
from datetime import datetime, timezone
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret")


class FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return self._rows


class FakeDb:
    def __init__(self, rows):
        self._rows = rows

    def query(self, _model):
        return FakeQuery(self._rows)


def _measure(metric, value):
    return {"metric": metric, "value": value}


def _build_sonar_dashboard_payload(run, db):
    from app.services.sonarqube_score_service import build_sonar_dashboard_payload

    return build_sonar_dashboard_payload(run, db)


def test_sonar_dashboard_payload_adds_dashboard_fields():
    run = SimpleNamespace(
        id=7,
        repository=SimpleNamespace(name="skill-pulse", full_name="acme/skill-pulse"),
        branch="main",
        triggered_at=datetime(2026, 6, 22, 10, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 6, 22, 10, 0, 32, tzinfo=timezone.utc),
        ai_insights={
            "project_key": "acme_skill-pulse",
            "sonar": {
                "quality_gate": {"projectStatus": {"status": "OK"}},
                "issues": {"issues": []},
                "file_measures": {
                    "components": [
                        {
                            "path": "services/order.py",
                            "measures": [
                                _measure("coverage", "32.43"),
                                _measure("duplicated_lines", "40"),
                                _measure("functions", "18"),
                            ],
                        }
                    ]
                },
                "measures": {
                    "component": {
                        "measures": [
                            _measure("bugs", "1"),
                            _measure("code_smells", "2"),
                            _measure("coverage", "68"),
                            _measure("line_coverage", "70.5"),
                            _measure("branch_coverage", "42"),
                            _measure("uncovered_lines", "10"),
                            _measure("duplicated_lines_density", "12"),
                            _measure("duplicated_lines", "40"),
                            _measure("duplicated_blocks", "3"),
                            _measure("duplicated_files", "2"),
                            _measure("complexity", "45"),
                            _measure("cognitive_complexity", "30"),
                            _measure("ncloc", "5800"),
                            _measure("files", "67"),
                            _measure("directories", "9"),
                            _measure("functions", "220"),
                            _measure("classes", "34"),
                            _measure("statements", "1420"),
                        ]
                    }
                },
            },
        },
    )
    rows = [
        SimpleNamespace(
            file_path="services/order.py",
            lines_of_code=320,
            cyclomatic_complexity=45,
            duplication_score=12,
            raw_metrics={
                "coverage": "68",
                "duplicated_lines": "40",
                "function_count": 18,
                "function_complexities": [
                    {"function": "process_order", "complexity": 18},
                    {"function": "calculate_discount", "cyclomatic": "15"},
                ],
            },
        )
    ]

    payload = _build_sonar_dashboard_payload(run, FakeDb(rows))

    assert payload["repository"]["duration_seconds"] == 32
    assert payload["project_size"] == {
        "lines_of_code": 5800,
        "files": 67,
        "directories": 9,
        "functions": 220,
        "classes": 34,
        "statements": 1420,
    }
    assert payload["file_metrics"] == [
        {
            "file": "services/order.py",
            "lines_of_code": 320,
            "complexity": 45,
            "duplication": 12,
            "coverage": 32.43,
            "duplicated_lines": 40,
            "functions": 18,
        }
    ]
    assert payload["complex_functions"] == [
        {"function": "process_order", "file": "services/order.py", "complexity": 18},
        {"function": "calculate_discount", "file": "services/order.py", "complexity": 15},
    ]


def test_sonar_dashboard_payload_handles_missing_sonar_and_raw_metrics():
    run = SimpleNamespace(
        id=8,
        repository=SimpleNamespace(name="skill-pulse", full_name="acme/skill-pulse"),
        branch="main",
        triggered_at=None,
        completed_at=None,
        ai_insights={},
    )
    rows = [
        SimpleNamespace(
            file_path="services/order.py",
            lines_of_code=None,
            cyclomatic_complexity=None,
            duplication_score=None,
            raw_metrics=None,
        )
    ]

    payload = _build_sonar_dashboard_payload(run, FakeDb(rows))

    assert payload["repository"]["duration_seconds"] is None
    assert payload["project_size"] == {
        "lines_of_code": None,
        "files": None,
        "directories": None,
        "functions": None,
        "classes": None,
        "statements": None,
    }
    assert payload["file_metrics"] == [
        {
            "file": "services/order.py",
            "lines_of_code": None,
            "complexity": None,
            "duplication": None,
            "coverage": None,
            "duplicated_lines": None,
            "functions": None,
        }
    ]
    assert payload["complex_functions"] == []


def test_sonar_dashboard_payload_uses_last_component_key_segment_for_paths():
    run = SimpleNamespace(
        id=9,
        repository=SimpleNamespace(name="flaskr-tdd-main", full_name="yasminyassen/updating"),
        branch="main",
        triggered_at=None,
        completed_at=None,
        ai_insights={
            "project_key": "skill-pulse:yasminyassen_updating:main",
            "sonar": {
                "quality_gate": {"projectStatus": {"status": "OK"}},
                "issues": {
                    "issues": [
                        {
                            "type": "BUG",
                            "severity": "MAJOR",
                            "component": "skill-pulse:yasminyassen_updating:main:project/templates/index.html",
                            "line": 12,
                            "message": "Fix this bug.",
                        },
                        {
                            "type": "CODE_SMELL",
                            "severity": "MINOR",
                            "component": "skill-pulse:yasminyassen_updating:main:project/app.py",
                            "textRange": {"startLine": 4},
                            "message": "Refactor this smell.",
                        },
                        {
                            "type": "VULNERABILITY",
                            "severity": "CRITICAL",
                            "component": "skill-pulse:yasminyassen_updating:main:project/security.py",
                            "message": "Not part of the Sonar dashboard issue set.",
                        },
                    ],
                },
                "file_measures": {
                    "components": [
                        {
                            "key": "skill-pulse:yasminyassen_updating:main:project/templates/index.html",
                            "measures": [_measure("coverage", "82")],
                        }
                    ]
                },
                "measures": {
                    "component": {
                        "measures": [
                            _measure("bugs", "1"),
                            _measure("code_smells", "1"),
                        ]
                    }
                },
            },
        },
    )

    payload = _build_sonar_dashboard_payload(run, FakeDb([]))

    assert payload["reliability"]["issues"] == [
        {
            "type": "BUG",
            "severity": "MAJOR",
            "file": "project/templates/index.html",
            "line": 12,
            "message": "Fix this bug.",
        }
    ]
    assert payload["maintainability"]["issues"] == [
        {
            "type": "CODE_SMELL",
            "severity": "MINOR",
            "file": "project/app.py",
            "line": 4,
            "message": "Refactor this smell.",
        }
    ]
    assert payload["issues_explorer"] == [
        *payload["reliability"]["issues"],
        *payload["maintainability"]["issues"],
    ]
    assert payload["file_metrics"][0]["file"] == "project/templates/index.html"
