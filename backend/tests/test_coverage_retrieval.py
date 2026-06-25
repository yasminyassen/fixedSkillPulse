"""Tests for deterministic coverage retrieval reranking."""

from ai_services.requirements.coverage import retrieval
from ai_services.requirements.coverage.retrieval import (
    merge_task_code_hits,
    rerank_code_hits,
    retrieve_code_for_acceptance_criterion_with_linked_tasks,
)


def test_rerank_prefers_symbol_and_path_match():
    query = "Technical task: allow developers to view assigned tasks\nLinked acceptance criteria:\n- Developer can view assigned tasks"
    hits = [
        {
            "file_path": "backend/app/tasks/routes.py",
            "symbol_name": "list_tasks",
            "chunk_id": "generic",
            "chunk_text": "def list_tasks(): return task_repo.all()",
            "score": 0.82,
        },
        {
            "file_path": "backend/app/tasks/routes.py",
            "symbol_name": "my_tasks_endpoint",
            "chunk_id": "my_tasks",
            "chunk_text": "def my_tasks_endpoint(current_user): return task_repo.assigned_to(current_user.id)",
            "score": 0.78,
        },
        {
            "file_path": "frontend/src/pages/MyTasks.tsx",
            "symbol_name": "MyTasks",
            "chunk_id": "my_tasks_ui",
            "chunk_text": "export function MyTasks() { return useAssignedTasks(); }",
            "score": 0.76,
        },
    ]

    ranked = rerank_code_hits(query, hits, top_k=3)

    assert ranked[0]["chunk_id"] in {"my_tasks", "my_tasks_ui"}
    assert ranked[0]["lexical_score"] > 0


def test_view_assigned_tasks_prefers_view_evidence_over_assignment():
    query = "Developers shall be able to view their assigned tasks."
    hits = [
        {
            "file_path": "backend/task_service.py",
            "symbol_name": "reassign_task",
            "chunk_id": "reassign",
            "chunk_text": "def reassign_task(task, new_developer_id): task.assigned_to = new_developer_id",
            "score": 0.58,
        },
        {
            "file_path": "backend/task_routes.py",
            "symbol_name": "my_tasks_endpoint",
            "chunk_id": "my_tasks",
            "chunk_text": 'def my_tasks_endpoint(): """View assigned tasks""" return get_tasks_for_user(1)',
            "score": 0.56,
        },
        {
            "file_path": "backend/task_service.py",
            "symbol_name": "assign_task",
            "chunk_id": "assign",
            "chunk_text": "def assign_task(task, developer_id): task.assigned_to = developer_id",
            "score": 0.57,
        },
    ]

    ranked = rerank_code_hits(query, hits, top_k=3)

    assert ranked[0]["chunk_id"] == "my_tasks"
    assert ranked[0]["lexical_score"] > ranked[1]["lexical_score"]


def test_assign_and_reassign_are_not_equivalent_actions():
    assign_query = "Managers shall be able to assign tasks to developers."
    reassign_query = "Managers shall be able to reassign tasks to other developers."
    hits = [
        {
            "file_path": "backend/task_service.py",
            "symbol_name": "assign_task",
            "chunk_id": "assign",
            "chunk_text": "def assign_task(task, developer_id): task.assigned_to = developer_id",
            "score": 0.55,
        },
        {
            "file_path": "backend/task_service.py",
            "symbol_name": "reassign_task",
            "chunk_id": "reassign",
            "chunk_text": "def reassign_task(task, new_developer_id): task.assigned_to = new_developer_id",
            "score": 0.55,
        },
    ]

    assert rerank_code_hits(assign_query, hits, top_k=2)[0]["chunk_id"] == "assign"
    assert rerank_code_hits(reassign_query, hits, top_k=2)[0]["chunk_id"] == "reassign"


def test_implementation_code_ranks_above_tests_when_behavior_matches():
    query = "Managers shall be able to assign tasks to developers."
    hits = [
        {
            "file_path": "tests/test_tasks.py",
            "symbol_name": "test_assign_task",
            "chunk_id": "test_assign",
            "chunk_text": "def test_assign_task(): assign_task(task, 1)",
            "score": 0.62,
        },
        {
            "file_path": "backend/task_routes.py",
            "symbol_name": "assign_task_endpoint",
            "chunk_id": "route_assign",
            "chunk_text": "def assign_task_endpoint(): return assign_task(task={}, developer_id=1)",
            "score": 0.58,
        },
    ]

    ranked = rerank_code_hits(query, hits, top_k=2)

    assert ranked[0]["chunk_id"] == "route_assign"
    assert ranked[0]["lexical_score"] > ranked[1]["lexical_score"]


def test_generic_domain_verbs_and_objects_drive_reranking():
    hits = [
        {
            "file_path": "backend/request_service.py",
            "symbol_name": "reject_request",
            "chunk_id": "reject",
            "chunk_text": "def reject_request(request_id): return update_request_status(request_id, 'rejected')",
            "score": 0.60,
        },
        {
            "file_path": "backend/request_service.py",
            "symbol_name": "approve_request",
            "chunk_id": "approve",
            "chunk_text": "def approve_request(request_id): return update_request_status(request_id, 'approved')",
            "score": 0.58,
        },
        {
            "file_path": "frontend/Reports.tsx",
            "symbol_name": "ExportReports",
            "chunk_id": "export_reports",
            "chunk_text": "export function ExportReports() { return <button>Export reports</button>; }",
            "score": 0.50,
        },
    ]

    approve_ranked = rerank_code_hits("Managers shall approve requests.", hits, top_k=3)
    export_ranked = rerank_code_hits("Users shall export reports.", hits, top_k=3)

    assert approve_ranked[0]["chunk_id"] == "approve"
    assert export_ranked[0]["chunk_id"] == "export_reports"


def test_generic_intent_extractor_skips_actor_between_allow_and_verb():
    verbs, objects = retrieval._intent_signals(
        "The system shall allow managers to create technical tasks with title and priority.",
        requirement_text=True,
    )

    assert "create" in verbs
    assert "manager" not in verbs
    assert {"title", "priority"} <= objects


def test_generic_intent_extractor_normalizes_stored_to_store():
    verbs, objects = retrieval._intent_signals(
        "Task ownership history shall be stored.",
        requirement_text=True,
    )

    assert "store" in verbs
    assert {"ownership", "history"} <= objects


def test_frontend_display_components_contribute_view_intent():
    verbs, objects = retrieval._intent_signals(
        "function MyTasks() { return <div><h1>My Assigned Tasks</h1><table><tbody><tr><td>Assigned</td></tr></tbody></table></div>; }",
        symbol_name="MyTasks",
        file_path="frontend/MyTasks.tsx",
    )

    assert {"view", "display", "list"} <= verbs
    assert "assign" in objects


def test_frontend_display_intent_is_generic_not_task_specific():
    hits = [
        {
            "file_path": "backend/request_service.py",
            "symbol_name": "approve_request",
            "chunk_id": "approve",
            "chunk_text": "def approve_request(request_id): return update_status(request_id, 'approved')",
            "score": 0.58,
        },
        {
            "file_path": "frontend/Reports.tsx",
            "symbol_name": "Reports",
            "chunk_id": "reports_ui",
            "chunk_text": "export function Reports() { return <section><h1>Reports</h1><table><tbody>{reports.map(report => <tr><td>{report.title}</td></tr>)}</tbody></table></section>; }",
            "score": 0.54,
        },
    ]

    ranked = rerank_code_hits("Users shall view reports.", hits, top_k=5)

    assert ranked[0]["chunk_id"] == "reports_ui"
    assert "view" in retrieval._intent_signals(
        hits[1]["chunk_text"],
        symbol_name=hits[1]["symbol_name"],
        file_path=hits[1]["file_path"],
    )[0]


def test_adaptive_evidence_selection_drops_low_relevance_tail():
    query = "The system shall allow managers to create technical tasks with title, description, and priority."
    hits = [
        {
            "file_path": "backend/task_service.py",
            "symbol_name": "create_task",
            "chunk_id": "create",
            "chunk_text": "def create_task(title, description, priority): return Task(title, description, priority)",
            "score": 0.58,
        },
        {
            "file_path": "backend/task_model.py",
            "symbol_name": "Task",
            "chunk_id": "model",
            "chunk_text": "class Task: title: str; description: str; priority: str",
            "score": 0.50,
        },
        {
            "file_path": "backend/task_service.py",
            "symbol_name": "assign_task",
            "chunk_id": "assign",
            "chunk_text": "def assign_task(task, developer_id): task.assigned_to = developer_id",
            "score": 0.48,
        },
    ]

    ranked = rerank_code_hits(query, hits, top_k=5)
    chunk_ids = [hit["chunk_id"] for hit in ranked]

    assert chunk_ids == ["create", "model"]
    assert "assign" not in chunk_ids


def test_merge_task_code_hits_diversifies_files():
    hits_by_task = [
        [
            {"file_path": "a.py", "chunk_id": "a1", "rerank_score": 0.99},
            {"file_path": "a.py", "chunk_id": "a2", "rerank_score": 0.98},
            {"file_path": "a.py", "chunk_id": "a3", "rerank_score": 0.97},
        ],
        [
            {"file_path": "b.py", "chunk_id": "b1", "rerank_score": 0.80},
            {"file_path": "frontend/MyTasks.tsx", "chunk_id": "ui1", "rerank_score": 0.79},
        ],
    ]

    merged = merge_task_code_hits(hits_by_task, max_chunks=4)
    files = [hit["file_path"] for hit in merged]

    assert "b.py" in files
    assert "frontend/MyTasks.tsx" in files


def test_manager_retrieval_query_is_ac_only(monkeypatch):
    captured = {}

    def fake_retrieve(run_id, query_text, top_k):
        captured["run_id"] = run_id
        captured["query_text"] = query_text
        captured["top_k"] = top_k
        return []

    monkeypatch.setattr(retrieval, "retrieve_code_for_task", fake_retrieve)

    retrieval.retrieve_code_for_acceptance_criterion(
        run_id=42,
        ac_text="Managers can reassign tasks between developers.",
        top_k=5,
    )

    assert captured == {
        "run_id": 42,
        "query_text": "Managers can reassign tasks between developers.",
        "top_k": 5,
    }


def test_developer_retrieval_query_is_task_only(monkeypatch):
    calls = []
    meta = [
        {
            "file_path": "backend/tasks/services.py",
            "symbol_name": "get_assigned_tasks",
            "symbol_type": "function",
            "chunk_id": "assigned_impl",
            "chunk_text": "def get_assigned_tasks(user_id): return task_repo.assigned_to(user_id)",
        },
        {
            "file_path": "frontend/MyTasks.tsx",
            "symbol_name": "MyTasks",
            "symbol_type": "function_declaration",
            "chunk_id": "assigned_ui",
            "chunk_text": "export function MyTasks(){ return <table>{tasks.map(task => <tr>{task.title}</tr>)}</table> }",
        },
    ]

    def fake_load_code_index(run_id):
        return object(), meta

    def fake_search_index(index, query_text, search_meta, top_k):
        calls.append(query_text)
        return [(0, 0.82, search_meta[0]), (1, 0.76, search_meta[1])]

    monkeypatch.setattr(retrieval, "load_code_index", fake_load_code_index)
    monkeypatch.setattr(retrieval, "search_index", fake_search_index)

    evidence = retrieval.retrieve_code_for_developer_task(
        run_id=43,
        task_description="Implement the assigned tasks endpoint.",
        linked_ac_texts=["Developers shall be able to view assigned tasks."],
        top_k=6,
    )

    assert calls == ["Implement the assigned tasks endpoint."]
    assert [hit["chunk_id"] for hit in evidence] == ["assigned_impl", "assigned_ui"]


def test_developer_retrieval_uses_linked_ac_fallback_when_task_evidence_is_weak(monkeypatch):
    calls = []
    meta = [
        {
            "file_path": "backend/leave/models.py",
            "symbol_name": "LeaveRequest",
            "symbol_type": "class",
            "chunk_id": "leave_model",
            "chunk_text": "class LeaveRequest: pass",
        },
        {
            "file_path": "backend/leave/services.py",
            "symbol_name": "submit_leave_request",
            "symbol_type": "function",
            "chunk_id": "submit_impl",
            "chunk_text": "def submit_leave_request(employee_id, dates): request = LeaveRequest(employee_id, dates); db.save(request); return request",
        },
    ]

    def fake_load_code_index(run_id):
        return object(), meta

    def fake_search_index(index, query_text, search_meta, top_k):
        calls.append(query_text)
        if "Employees shall submit leave requests" in query_text:
            return [(1, 0.75, search_meta[1]), (0, 0.45, search_meta[0])]
        return [(0, 0.41, search_meta[0])]

    monkeypatch.setattr(retrieval, "load_code_index", fake_load_code_index)
    monkeypatch.setattr(retrieval, "search_index", fake_search_index)

    evidence = retrieval.retrieve_code_for_developer_task(
        run_id=43,
        task_description="Implement employee leave intake.",
        linked_ac_texts=["Employees shall submit leave requests with date ranges."],
    )

    assert calls == [
        "Implement employee leave intake.",
        "Employees shall submit leave requests with date ranges.",
    ]
    assert evidence[0]["chunk_id"] == "submit_impl"
    assert "linked_ac" in evidence[0]["retrieval_source"]


def test_developer_retrieval_applies_call_neighbor_expansion(monkeypatch):
    meta = [
        {
            "file_path": "backend/leave/services.py",
            "symbol_name": "approve_leave_request",
            "symbol_type": "function",
            "chunk_id": "approve_impl",
            "chunk_text": "def approve_leave_request(request_id): publish_leave_decision(request_id); return save_approval(request_id)",
        },
        {
            "file_path": "backend/leave/publishers.py",
            "symbol_name": "publish_leave_decision",
            "symbol_type": "function",
            "chunk_id": "publish_impl",
            "chunk_text": "def publish_leave_decision(request_id): event_bus.publish('leave.approved', request_id)",
        },
    ]

    def fake_load_code_index(run_id):
        return object(), meta

    def fake_search_index(index, query_text, search_meta, top_k):
        return [(0, 0.82, search_meta[0])]

    monkeypatch.setattr(retrieval, "load_code_index", fake_load_code_index)
    monkeypatch.setattr(retrieval, "search_index", fake_search_index)

    evidence = retrieval.retrieve_code_for_developer_task(
        run_id=43,
        task_description="Implement leave approval notification.",
        linked_ac_texts=[],
    )

    assert [hit["chunk_id"] for hit in evidence] == ["approve_impl", "publish_impl"]
    assert evidence[1]["retrieval_source"] == "call_neighbor"
    assert evidence[1]["neighbor_reason"] == "direct_call:publish_leave_decision"


def test_developer_retrieval_allows_eight_evidence_chunks(monkeypatch):
    meta = [
        {
            "file_path": f"backend/reports/service_{idx}.py",
            "symbol_name": f"export_report_part_{idx}",
            "symbol_type": "function",
            "chunk_id": f"chunk_{idx}",
            "chunk_text": f"def export_report_part_{idx}(): return report_export_pipeline.step_{idx}()",
        }
        for idx in range(9)
    ]

    def fake_load_code_index(run_id):
        return object(), meta

    def fake_search_index(index, query_text, search_meta, top_k):
        return [
            (idx, 0.92 - (idx * 0.01), search_meta[idx])
            for idx in range(min(top_k, len(search_meta)))
        ]

    monkeypatch.setattr(retrieval, "load_code_index", fake_load_code_index)
    monkeypatch.setattr(retrieval, "search_index", fake_search_index)

    evidence = retrieval.retrieve_code_for_developer_task(
        run_id=43,
        task_description="Implement export report pipeline with validation persistence and integrations.",
        linked_ac_texts=[],
    )

    assert len(evidence) == 8
    assert [hit["chunk_id"] for hit in evidence] == [f"chunk_{idx}" for idx in range(8)]


def test_developer_retrieval_allows_broad_backend_task_from_same_file(monkeypatch):
    meta = [
        {
            "file_path": "backend/task_service.py",
            "symbol_name": symbol,
            "symbol_type": "function",
            "chunk_id": chunk_id,
            "chunk_text": text,
        }
        for symbol, chunk_id, text in [
            ("create_task", "create", "def create_task(title, description, priority): return Task(title, description, priority)"),
            ("assign_task", "assign", "def assign_task(task_id, developer_id): task.assigned_to = developer_id; save(task)"),
            ("reassign_task", "reassign", "def reassign_task(task_id, developer_id): record_assignment_history(task_id); task.assigned_to = developer_id"),
            ("record_assignment_history", "history", "def record_assignment_history(task_id): AssignmentHistory.create(task_id=task_id)"),
            ("get_task", "get", "def get_task(task_id): return Task.query.get(task_id)"),
        ]
    ]

    def fake_load_code_index(run_id):
        return object(), meta

    def fake_search_index(index, query_text, search_meta, top_k):
        assert top_k == retrieval.DEFAULT_DEVELOPER_TASK_TO_CODE_CANDIDATES
        return [
            (idx, 0.92 - (idx * 0.02), search_meta[idx])
            for idx in range(len(search_meta))
        ]

    monkeypatch.setattr(retrieval, "load_code_index", fake_load_code_index)
    monkeypatch.setattr(retrieval, "search_index", fake_search_index)

    evidence = retrieval.retrieve_code_for_developer_task(
        run_id=43,
        task_description="Implement backend API for task creation, assignment, reassignment, and ownership history tracking",
        linked_ac_texts=[],
        top_k=8,
        include_call_neighbors=False,
    )

    chunk_ids = [hit["chunk_id"] for hit in evidence]
    assert {"create", "assign", "reassign", "history"}.issubset(set(chunk_ids))
    assert len([hit for hit in evidence if hit["file_path"] == "backend/task_service.py"]) > 3


def test_adaptive_fallback_selection_fills_remaining_budget():
    hits = [
        {"file_path": "a.py", "chunk_id": "strong", "rerank_score": 0.48},
        {"file_path": "b.py", "chunk_id": "fallback_1", "rerank_score": 0.44},
        {"file_path": "c.py", "chunk_id": "fallback_2", "rerank_score": 0.43},
        {"file_path": "d.py", "chunk_id": "fallback_3", "rerank_score": 0.42},
        {"file_path": "e.py", "chunk_id": "too_weak", "rerank_score": 0.34},
    ]

    selected = retrieval._select_adaptive_evidence(hits, max_evidence=4)

    assert [hit["chunk_id"] for hit in selected] == ["strong", "fallback_1", "fallback_2", "fallback_3"]


def test_linked_task_expansion_recovers_implementation_when_primary_is_weak(monkeypatch):
    meta = [
        {
            "file_path": "backend/approvals/models.py",
            "symbol_name": "ApprovalDecision",
            "symbol_type": "class",
            "chunk_id": "decision_model",
            "chunk_text": "class ApprovalDecision: pass",
        },
        {
            "file_path": "backend/approvals/services.py",
            "symbol_name": "reject_request",
            "symbol_type": "function",
            "chunk_id": "reject_impl",
            "chunk_text": "def reject_request(request, reviewer_id, comment): request.status = 'rejected'; save_decision(comment)",
        },
    ]

    def fake_load_code_index(run_id):
        return object(), meta

    def fake_search_index(index, query_text, search_meta, top_k):
        if "approval decision workflow" in query_text:
            return [(1, 0.72, search_meta[1]), (0, 0.51, search_meta[0])]
        return [(0, 0.42, search_meta[0])]

    monkeypatch.setattr(retrieval, "load_code_index", fake_load_code_index)
    monkeypatch.setattr(retrieval, "search_index", fake_search_index)

    evidence = retrieve_code_for_acceptance_criterion_with_linked_tasks(
        1,
        "Managers shall be able to reject requests.",
        ["Implement approval decision workflow."],
    )

    assert evidence[0]["chunk_id"] == "reject_impl"
    assert "linked_task" in evidence[0]["retrieval_source"]


def test_linked_task_expansion_does_not_run_when_primary_is_strong(monkeypatch):
    meta = [
        {
            "file_path": "backend/approvals/services.py",
            "symbol_name": "reject_request",
            "symbol_type": "function",
            "chunk_id": "reject_impl",
            "chunk_text": "def reject_request(request, reviewer_id, comment): request.status = 'rejected'; save_decision(comment)",
        },
        {
            "file_path": "frontend/ApprovalQueue.tsx",
            "symbol_name": "ApprovalQueue",
            "symbol_type": "function_declaration",
            "chunk_id": "queue_ui",
            "chunk_text": "export function ApprovalQueue(){ return <table><tbody>{requests.map(request => <tr><td>Reject</td></tr>)}</tbody></table>; }",
        },
    ]
    calls = []

    def fake_load_code_index(run_id):
        return object(), meta

    def fake_search_index(index, query_text, search_meta, top_k):
        calls.append(query_text)
        return [(0, 0.8, search_meta[0]), (1, 0.7, search_meta[1])]

    monkeypatch.setattr(retrieval, "load_code_index", fake_load_code_index)
    monkeypatch.setattr(retrieval, "search_index", fake_search_index)

    evidence = retrieve_code_for_acceptance_criterion_with_linked_tasks(
        1,
        "Managers shall be able to reject requests.",
        ["Implement approval decision workflow."],
    )

    assert [hit["chunk_id"] for hit in evidence] == ["reject_impl", "queue_ui"]
    assert calls == ["Managers shall be able to reject requests."]


def test_linked_task_expansion_does_not_run_for_low_score_primary_with_enough_implementation(monkeypatch):
    meta = [
        {
            "file_path": "backend/approvals/services.py",
            "symbol_name": "reject_request",
            "symbol_type": "function",
            "chunk_id": "reject_impl",
            "chunk_text": "def reject_request(request, reviewer_id): request.status = 'rejected'; save_request(request)",
        },
        {
            "file_path": "frontend/ApprovalQueue.tsx",
            "symbol_name": "ApprovalQueue",
            "symbol_type": "function_declaration",
            "chunk_id": "queue_ui",
            "chunk_text": "export function ApprovalQueue(){ return <table><tbody>{requests.map(request => <tr><td>Reject</td></tr>)}</tbody></table>; }",
        },
    ]
    calls = []

    def fake_load_code_index(run_id):
        return object(), meta

    def fake_search_index(index, query_text, search_meta, top_k):
        calls.append(query_text)
        return [(0, 0.36, search_meta[0]), (1, 0.35, search_meta[1])]

    monkeypatch.setattr(retrieval, "load_code_index", fake_load_code_index)
    monkeypatch.setattr(retrieval, "search_index", fake_search_index)

    evidence = retrieve_code_for_acceptance_criterion_with_linked_tasks(
        1,
        "Managers shall be able to reject requests.",
        ["Implement approval decision workflow."],
    )

    assert [hit["chunk_id"] for hit in evidence] == ["reject_impl", "queue_ui"]
    assert calls == ["Managers shall be able to reject requests."]


def test_call_neighbor_expansion_recovers_called_project_local_symbol(monkeypatch):
    meta = [
        {
            "file_path": "backend/approvals/services.py",
            "symbol_name": "approve_request",
            "symbol_type": "function",
            "chunk_id": "approve_impl",
            "chunk_text": "def approve_request(request_id): publish_notification(request_id); return save_approval(request_id)",
            "start_line": 1,
            "end_line": 2,
        },
        {
            "file_path": "backend/notifications/publishers.py",
            "symbol_name": "publish_notification",
            "symbol_type": "function",
            "chunk_id": "notification_impl",
            "chunk_text": "def publish_notification(request_id): event_bus.publish('approval.changed', {'request_id': request_id})",
            "start_line": 1,
            "end_line": 2,
        },
    ]

    def fake_load_code_index(run_id):
        return object(), meta

    def fake_search_index(index, query_text, search_meta, top_k):
        return [(0, 0.82, search_meta[0])]

    monkeypatch.setattr(retrieval, "load_code_index", fake_load_code_index)
    monkeypatch.setattr(retrieval, "search_index", fake_search_index)

    evidence = retrieve_code_for_acceptance_criterion_with_linked_tasks(
        1,
        "Request owners shall be notified when an approval decision is made.",
        [],
        include_call_neighbors=True,
    )

    assert [hit["chunk_id"] for hit in evidence] == ["approve_impl", "notification_impl"]
    assert evidence[0]["retrieval_source"] == "primary"
    assert evidence[1]["retrieval_source"] == "call_neighbor"
    assert evidence[1]["neighbor_reason"] == "direct_call:publish_notification"


def test_call_neighbor_expansion_is_enabled_by_default_for_manager_scoring(monkeypatch):
    meta = [
        {
            "file_path": "backend/approvals/services.py",
            "symbol_name": "approve_request",
            "symbol_type": "function",
            "chunk_id": "approve_impl",
            "chunk_text": "def approve_request(request_id): publish_notification(request_id); return save_approval(request_id)",
            "start_line": 1,
            "end_line": 2,
        },
        {
            "file_path": "backend/notifications/publishers.py",
            "symbol_name": "publish_notification",
            "symbol_type": "function",
            "chunk_id": "notification_impl",
            "chunk_text": "def publish_notification(request_id): event_bus.publish('approval.changed', {'request_id': request_id})",
            "start_line": 1,
            "end_line": 2,
        },
    ]

    def fake_load_code_index(run_id):
        return object(), meta

    def fake_search_index(index, query_text, search_meta, top_k):
        return [(0, 0.82, search_meta[0])]

    monkeypatch.setattr(retrieval, "load_code_index", fake_load_code_index)
    monkeypatch.setattr(retrieval, "search_index", fake_search_index)

    evidence = retrieve_code_for_acceptance_criterion_with_linked_tasks(
        1,
        "Request owners shall be notified when an approval decision is made.",
        [],
    )

    assert [hit["chunk_id"] for hit in evidence] == ["approve_impl", "notification_impl"]
    assert evidence[1]["retrieval_source"] == "call_neighbor"


def test_call_neighbor_expansion_does_not_relabel_already_selected_callee(monkeypatch):
    meta = [
        {
            "file_path": "backend/approvals/services.py",
            "symbol_name": "approve_request",
            "symbol_type": "function",
            "chunk_id": "approve_impl",
            "chunk_text": "def approve_request(request_id): publish_notification(request_id); return save_approval(request_id)",
            "start_line": 1,
            "end_line": 2,
        },
        {
            "file_path": "backend/notifications/publishers.py",
            "symbol_name": "publish_notification",
            "symbol_type": "function",
            "chunk_id": "notification_impl",
            "chunk_text": "def publish_notification(request_id): event_bus.publish('approval.changed', {'request_id': request_id})",
            "start_line": 1,
            "end_line": 2,
        },
    ]

    def fake_load_code_index(run_id):
        return object(), meta

    def fake_search_index(index, query_text, search_meta, top_k):
        return [(0, 0.82, search_meta[0]), (1, 0.66, search_meta[1])]

    monkeypatch.setattr(retrieval, "load_code_index", fake_load_code_index)
    monkeypatch.setattr(retrieval, "search_index", fake_search_index)

    evidence = retrieve_code_for_acceptance_criterion_with_linked_tasks(
        1,
        "Request owners shall be notified when an approval decision is made.",
        [],
        include_call_neighbors=True,
    )

    assert [hit["chunk_id"] for hit in evidence] == ["approve_impl", "notification_impl"]
    assert evidence[1]["retrieval_source"] == "primary"


def test_call_neighbor_expansion_does_not_add_adjacent_sibling_symbol(monkeypatch):
    meta = [
        {
            "file_path": "backend/tasks/services.py",
            "symbol_name": "create_task",
            "symbol_type": "function",
            "chunk_id": "create_impl",
            "chunk_text": "def create_task(title): return Task(title=title)",
            "start_line": 1,
            "end_line": 2,
        },
        {
            "file_path": "backend/tasks/services.py",
            "symbol_name": "assign_task",
            "symbol_type": "function",
            "chunk_id": "assign_impl",
            "chunk_text": "def assign_task(task_id, developer_id): task.assignee_id = developer_id",
            "start_line": 4,
            "end_line": 5,
        },
    ]

    def fake_load_code_index(run_id):
        return object(), meta

    def fake_search_index(index, query_text, search_meta, top_k):
        return [(0, 0.8, search_meta[0])]

    monkeypatch.setattr(retrieval, "load_code_index", fake_load_code_index)
    monkeypatch.setattr(retrieval, "search_index", fake_search_index)

    evidence = retrieve_code_for_acceptance_criterion_with_linked_tasks(
        1,
        "Managers shall be able to create tasks.",
        [],
        include_call_neighbors=True,
    )

    assert [hit["chunk_id"] for hit in evidence] == ["create_impl"]


def test_call_neighbor_expansion_does_not_replace_when_evidence_budget_is_full(monkeypatch):
    meta = [
        {
            "file_path": "backend/approvals/services.py",
            "symbol_name": "approve_request",
            "symbol_type": "function",
            "chunk_id": "approve_impl",
            "chunk_text": "def approve_request(request_id): publish_notification(request_id); return save_approval(request_id)",
            "start_line": 1,
            "end_line": 2,
        },
        {
            "file_path": "backend/approvals/models.py",
            "symbol_name": "ApprovalDecision",
            "symbol_type": "class",
            "chunk_id": "decision_model",
            "chunk_text": "class ApprovalDecision: pass",
            "start_line": 1,
            "end_line": 2,
        },
        {
            "file_path": "backend/notifications/publishers.py",
            "symbol_name": "publish_notification",
            "symbol_type": "function",
            "chunk_id": "notification_impl",
            "chunk_text": "def publish_notification(request_id): event_bus.publish('approval.changed', {'request_id': request_id})",
            "start_line": 1,
            "end_line": 2,
        },
    ]

    def fake_load_code_index(run_id):
        return object(), meta

    def fake_search_index(index, query_text, search_meta, top_k):
        return [(0, 0.82, search_meta[0]), (1, 0.35, search_meta[1])]

    monkeypatch.setattr(retrieval, "load_code_index", fake_load_code_index)
    monkeypatch.setattr(retrieval, "search_index", fake_search_index)

    evidence = retrieve_code_for_acceptance_criterion_with_linked_tasks(
        1,
        "Request owners shall be notified when an approval decision is made.",
        [],
        top_k=2,
        include_call_neighbors=True,
    )

    assert [hit["chunk_id"] for hit in evidence] == ["approve_impl", "decision_model"]
    assert len(evidence) == 2
    assert all(hit["retrieval_source"] == "primary" for hit in evidence)


def test_imported_project_local_symbol_expansion_recovers_imported_implementation(monkeypatch):
    meta = [
        {
            "file_path": "backend/approvals/services.py",
            "symbol_name": "approve_request",
            "symbol_type": "function",
            "chunk_id": "approve_impl",
            "chunk_text": "from notification_service import publish_notification\n\ndef approve_request(request_id): return save_approval(request_id)",
            "start_line": 1,
            "end_line": 3,
        },
        {
            "file_path": "backend/notifications/notification_service.py",
            "symbol_name": "publish_notification",
            "symbol_type": "function",
            "chunk_id": "notification_impl",
            "chunk_text": "def publish_notification(request_id): event_bus.publish('approval.changed', {'request_id': request_id})",
            "start_line": 1,
            "end_line": 2,
        },
    ]

    def fake_load_code_index(run_id):
        return object(), meta

    def fake_search_index(index, query_text, search_meta, top_k):
        return [(0, 0.82, search_meta[0])]

    monkeypatch.setattr(retrieval, "load_code_index", fake_load_code_index)
    monkeypatch.setattr(retrieval, "search_index", fake_search_index)

    evidence = retrieve_code_for_acceptance_criterion_with_linked_tasks(
        1,
        "Request owners shall be notified when an approval decision is made.",
        [],
    )

    assert [hit["chunk_id"] for hit in evidence] == ["approve_impl", "notification_impl"]
    assert evidence[1]["retrieval_source"] == "call_neighbor"
    assert evidence[1]["neighbor_reason"] == "imported_symbol:publish_notification"


def test_imported_project_local_symbol_expansion_can_add_multiple_dependencies(monkeypatch):
    meta = [
        {
            "file_path": "backend/approvals/services.py",
            "symbol_name": "approve_request",
            "symbol_type": "function",
            "chunk_id": "approve_impl",
            "chunk_text": (
                "from notification_service import publish_notification\n"
                "from audit_service import record_audit_event\n\n"
                "def approve_request(request_id): return save_approval(request_id)"
            ),
            "start_line": 1,
            "end_line": 4,
        },
        {
            "file_path": "backend/notifications/notification_service.py",
            "symbol_name": "publish_notification",
            "symbol_type": "function",
            "chunk_id": "notification_impl",
            "chunk_text": "def publish_notification(request_id): event_bus.publish('approval.changed', {'request_id': request_id})",
            "start_line": 1,
            "end_line": 2,
        },
        {
            "file_path": "backend/audit/audit_service.py",
            "symbol_name": "record_audit_event",
            "symbol_type": "function",
            "chunk_id": "audit_impl",
            "chunk_text": "def record_audit_event(request_id): audit_log.write({'request_id': request_id, 'event': 'approval.changed'})",
            "start_line": 1,
            "end_line": 2,
        },
    ]

    def fake_load_code_index(run_id):
        return object(), meta

    def fake_search_index(index, query_text, search_meta, top_k):
        return [(0, 0.82, search_meta[0])]

    monkeypatch.setattr(retrieval, "load_code_index", fake_load_code_index)
    monkeypatch.setattr(retrieval, "search_index", fake_search_index)

    evidence = retrieve_code_for_acceptance_criterion_with_linked_tasks(
        1,
        "Request owners shall be notified when an approval decision is made.",
        [],
        top_k=3,
    )

    assert [hit["chunk_id"] for hit in evidence] == ["approve_impl", "audit_impl", "notification_impl"]
    assert len(evidence) == 3
    assert {hit["neighbor_reason"] for hit in evidence[1:]} == {
        "imported_symbol:record_audit_event",
        "imported_symbol:publish_notification",
    }
