import os
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("sendgrid_api_key", "test-sendgrid")
os.environ.setdefault("from_email", "test@example.com")

from app.api import requirement_coverage
from app.api.requirement_coverage import _attach_active_run_state, _empty_manager_dashboard, get_developer_coverage
from app.db.models import CoverageRunStatus


def _run(run_id: int, status: CoverageRunStatus):
    return SimpleNamespace(
        id=run_id,
        repository_id=1,
        document_id=1,
        analysis_run_id=7,
        status=status,
        overall_coverage=None,
        branch="main",
        commit_sha="abc123",
        created_at=None,
        completed_at=None,
        error_message=None,
        developer_task_results=[],
    )


def test_empty_manager_dashboard_does_not_fabricate_zero_coverage_results():
    payload = _empty_manager_dashboard()

    assert payload["run"] is None
    assert payload["summary"] is None
    assert payload["stories"] == []
    assert payload["is_analysis_running"] is False


def test_active_run_is_attached_without_replacing_completed_results():
    payload = {
        "run": {"id": 4, "status": "completed", "overall_coverage_percent": 80.0},
        "summary": {"implemented_stories": 1, "partially_implemented_stories": 0, "missing_stories": 0},
        "stories": [{"story_id": 1, "status": "implemented", "coverage_percent": 80.0}],
    }

    result = _attach_active_run_state(None, payload, _run(5, CoverageRunStatus.running))

    assert result["run"]["id"] == 4
    assert result["stories"][0]["status"] == "implemented"
    assert result["active_run"]["id"] == 5
    assert result["active_run"]["status"] == "running"
    assert result["is_analysis_running"] is True


def test_developer_coverage_uses_latest_completed_run(monkeypatch):
    completed = _run(4, CoverageRunStatus.completed)
    calls = {}

    def fake_latest_completed(db, repo_id):
        calls["repo_id"] = repo_id
        return completed

    def fake_dashboard(db, run, current_user):
        return {"run": {"id": run.id}, "stories": []}

    scheduled = []
    monkeypatch.setattr(requirement_coverage, "_latest_completed_coverage_run", fake_latest_completed)
    monkeypatch.setattr(requirement_coverage, "_build_developer_dashboard", fake_dashboard)

    result = get_developer_coverage(
        repo_id=99,
        background_tasks=SimpleNamespace(add_task=lambda *args, **kwargs: scheduled.append((args, kwargs))),
        db=object(),
        current_user=SimpleNamespace(id=12, role=SimpleNamespace(value="developer")),
    )

    assert calls["repo_id"] == 99
    assert result["run"]["id"] == 4
    assert scheduled
