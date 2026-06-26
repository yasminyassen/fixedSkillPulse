"""add recruiter tasks

Revision ID: n1o2p3q4r5s6
Revises: m1n2o3p4q5r6
Create Date: 2026-06-26 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "n1o2p3q4r5s6"
down_revision: Union[str, None] = "m1n2o3p4q5r6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_names(inspector, table_name: str) -> set[str]:
    if not inspector.has_table(table_name):
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def _foreign_key_names(inspector, table_name: str) -> set[str]:
    if not inspector.has_table(table_name):
        return set()
    return {fk["name"] for fk in inspector.get_foreign_keys(table_name) if fk.get("name")}


def _backfill_missing_tasks(bind) -> None:
    bind.execute(sa.text("""
        INSERT INTO recruiter_tasks (
            id,
            recruiter_id,
            title,
            csv_filename,
            total_candidates,
            valid_count,
            skipped_count,
            status,
            created_at,
            updated_at
        )
        SELECT
            grouped.task_id,
            grouped.recruiter_id,
            'Recovered Recruiter Batch ' || grouped.task_id,
            NULL,
            grouped.total_candidates,
            grouped.total_candidates,
            0,
            'completed',
            grouped.created_at,
            grouped.created_at
        FROM (
            SELECT
                rc.task_id,
                MIN(ar.user_id) AS recruiter_id,
                COUNT(*) AS total_candidates,
                COALESCE(MIN(rc.created_at), NOW()) AS created_at
            FROM recruiter_candidates rc
            JOIN analysis_runs ar ON ar.id = rc.analysis_run_id
            JOIN users u ON u.id = ar.user_id
            WHERE rc.task_id IS NOT NULL
            GROUP BY rc.task_id
        ) AS grouped
        WHERE NOT EXISTS (
            SELECT 1
            FROM recruiter_tasks rt
            WHERE rt.id = grouped.task_id
        )
    """))
    bind.execute(sa.text("""
        UPDATE recruiter_candidates rc
        SET task_id = NULL
        WHERE rc.task_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM recruiter_tasks rt
              WHERE rt.id = rc.task_id
          )
    """))
    bind.execute(sa.text("""
        SELECT setval(
            pg_get_serial_sequence('recruiter_tasks', 'id'),
            GREATEST(COALESCE((SELECT MAX(id) FROM recruiter_tasks), 0), 1),
            TRUE
        )
    """))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("recruiter_tasks"):
        op.create_table(
            "recruiter_tasks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("recruiter_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("csv_filename", sa.String(), nullable=True),
            sa.Column("total_candidates", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("valid_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        )
        inspector = inspect(bind)

    recruiter_task_indexes = _index_names(inspector, "recruiter_tasks")
    if "ix_recruiter_tasks_id" not in recruiter_task_indexes:
        op.create_index("ix_recruiter_tasks_id", "recruiter_tasks", ["id"], unique=False)
    if "ix_recruiter_tasks_recruiter_id" not in recruiter_task_indexes:
        op.create_index("ix_recruiter_tasks_recruiter_id", "recruiter_tasks", ["recruiter_id"], unique=False)

    candidate_columns = {c["name"] for c in inspector.get_columns("recruiter_candidates")}
    if "task_id" not in candidate_columns:
        op.add_column("recruiter_candidates", sa.Column("task_id", sa.Integer(), nullable=True))
        inspector = inspect(bind)

    _backfill_missing_tasks(bind)
    inspector = inspect(bind)

    candidate_foreign_keys = _foreign_key_names(inspector, "recruiter_candidates")
    if "fk_recruiter_candidates_task_id" not in candidate_foreign_keys:
        op.create_foreign_key(
            "fk_recruiter_candidates_task_id",
            "recruiter_candidates",
            "recruiter_tasks",
            ["task_id"],
            ["id"],
        )
        inspector = inspect(bind)

    candidate_indexes = _index_names(inspector, "recruiter_candidates")
    if "ix_recruiter_candidates_task_id" not in candidate_indexes:
        op.create_index("ix_recruiter_candidates_task_id", "recruiter_candidates", ["task_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table("recruiter_candidates"):
        candidate_indexes = _index_names(inspector, "recruiter_candidates")
        if "ix_recruiter_candidates_task_id" in candidate_indexes:
            op.drop_index("ix_recruiter_candidates_task_id", table_name="recruiter_candidates")

        candidate_columns = {c["name"] for c in inspector.get_columns("recruiter_candidates")}
        if "task_id" in candidate_columns:
            try:
                op.drop_constraint("fk_recruiter_candidates_task_id", "recruiter_candidates", type_="foreignkey")
            except Exception:
                pass
            op.drop_column("recruiter_candidates", "task_id")

    if inspector.has_table("recruiter_tasks"):
        recruiter_task_indexes = _index_names(inspector, "recruiter_tasks")
        if "ix_recruiter_tasks_recruiter_id" in recruiter_task_indexes:
            op.drop_index("ix_recruiter_tasks_recruiter_id", table_name="recruiter_tasks")
        if "ix_recruiter_tasks_id" in recruiter_task_indexes:
            op.drop_index("ix_recruiter_tasks_id", table_name="recruiter_tasks")
        op.drop_table("recruiter_tasks")
