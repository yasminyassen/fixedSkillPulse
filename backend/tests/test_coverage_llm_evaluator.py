from ai_services.requirements.coverage.llm_evaluator import _build_developer_task_prompt, _build_prompt


def test_coverage_prompt_uses_readiness_rubric():
    prompt = _build_prompt(
        story_title="Task management",
        story_description="Managers manage task ownership.",
        ac_text="Managers shall assign tasks to developers.",
        code_evidence=[
            {
                "file_path": "backend/task_routes.py",
                "start_line": 1,
                "end_line": 10,
                "chunk_text": "def assign_task_endpoint(): return assign_task(task={}, developer_id=1)",
            }
        ],
    )

    assert "Evaluate readiness, not simple code presence." in prompt
    assert "usable feature" in prompt
    assert "workflow end-to-end" in prompt
    assert "placeholder" in prompt
    assert "hardcoded" in prompt
    assert "static UI" in prompt
    assert "choose PARTIALLY_COVERED rather than COVERED" in prompt


def test_developer_task_prompt_uses_task_scope_rubric():
    prompt = _build_developer_task_prompt(
        task_description="Build Export Report Button",
        linked_acceptance_criteria=["Managers shall export reports as PDFs."],
        code_evidence=[
            {
                "file_path": "frontend/Reports.tsx",
                "start_line": 4,
                "end_line": 12,
                "chunk_text": "export function ExportReportButton(){ return <button onClick={exportReport}>Export</button> }",
            }
        ],
    )

    assert "assigned developer technical task" in prompt
    assert "Evaluate only whether the assigned technical task has been implemented." in prompt
    assert "Do not evaluate business requirement coverage" in prompt
    assert "Do not fail this task because another assigned task is incomplete." in prompt
    assert "Build Export Report Button" in prompt
    assert "COVERED: the assigned task is implemented and usable" in prompt
    assert "NOT_COVERED: the required task behavior is absent" in prompt
