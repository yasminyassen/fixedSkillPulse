"""repair requirement coverage schema

Revision ID: k1l2m3n4o5p6
Revises: j1k2l3m4n5o6
Create Date: 2026-06-24 00:00:00.000000

The shared database was stamped beyond the requirement coverage migrations
without actually having their tables. This forward-only repair makes the
current schema present while preserving existing data.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "k1l2m3n4o5p6"
down_revision: Union[str, None] = "i3j4k5l6m7n8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


coverage_run_status = postgresql.ENUM(
    "pending",
    "running",
    "completed",
    "failed",
    name="coveragerunstatus",
    create_type=False,
)
ac_coverage_status = postgresql.ENUM(
    "COVERED",
    "PARTIALLY_COVERED",
    "NOT_COVERED",
    name="accoveragestatus",
    create_type=False,
)
story_coverage_status = postgresql.ENUM(
    "implemented",
    "partially_implemented",
    "not_implemented",
    name="storycoveragestatus",
    create_type=False,
)


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return column_name in {column["name"] for column in _inspector().get_columns(table_name)}


def _index_exists(table_name: str, index_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return index_name in {index["name"] for index in _inspector().get_indexes(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if _table_exists(table_name) and not _column_exists(table_name, column.name):
        op.add_column(table_name, column)


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if _table_exists(table_name) and not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def _create_required_enums() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'coveragerunstatus') THEN
                CREATE TYPE coveragerunstatus AS ENUM ('pending', 'running', 'completed', 'failed');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'accoveragestatus') THEN
                CREATE TYPE accoveragestatus AS ENUM ('COVERED', 'PARTIALLY_COVERED', 'NOT_COVERED');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'storycoveragestatus') THEN
                CREATE TYPE storycoveragestatus AS ENUM (
                    'implemented',
                    'partially_implemented',
                    'not_implemented'
                );
            END IF;
        END
        $$;
        """
    )
    op.execute("ALTER TYPE documentstatus ADD VALUE IF NOT EXISTS 'confirmed'")


def _create_requirement_coverage_runs() -> None:
    if _table_exists("requirement_coverage_runs"):
        return

    op.create_table(
        "requirement_coverage_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("analysis_run_id", sa.Integer(), nullable=True),
        sa.Column("status", coverage_run_status, nullable=False),
        sa.Column("overall_coverage", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("discovery_links", sa.JSON(), nullable=True),
        sa.Column("developer_task_results", sa.JSON(), nullable=True),
        sa.Column("branch", sa.String(), nullable=True),
        sa.Column("commit_sha", sa.String(), nullable=True),
        sa.Column("requirements_snapshot_hash", sa.String(), nullable=True),
        sa.Column("tasks_snapshot_hash", sa.String(), nullable=True),
        sa.Column("assignments_snapshot_hash", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["requirement_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_code_embedding_records() -> None:
    if _table_exists("code_embedding_records"):
        return

    op.create_table(
        "code_embedding_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("coverage_run_id", sa.Integer(), nullable=False),
        sa.Column("faiss_id", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("symbol_name", sa.String(), nullable=True),
        sa.Column("symbol_type", sa.String(), nullable=True),
        sa.Column("chunk_id", sa.String(), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=True),
        sa.Column("end_line", sa.Integer(), nullable=True),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["coverage_run_id"], ["requirement_coverage_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_task_embedding_records() -> None:
    if _table_exists("task_embedding_records"):
        return

    op.create_table(
        "task_embedding_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("coverage_run_id", sa.Integer(), nullable=False),
        sa.Column("faiss_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("story_id", sa.Integer(), nullable=False),
        sa.Column("embedding_text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["coverage_run_id"], ["requirement_coverage_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["story_id"], ["user_stories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["technical_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_ac_coverage_results() -> None:
    if _table_exists("ac_coverage_results"):
        return

    op.create_table(
        "ac_coverage_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("coverage_run_id", sa.Integer(), nullable=False),
        sa.Column("story_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("ac_id", sa.Integer(), nullable=False),
        sa.Column("status", ac_coverage_status, nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("matched_chunk_ids", sa.JSON(), nullable=True),
        sa.Column("llm_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["coverage_run_id"], ["requirement_coverage_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["story_id"], ["user_stories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["technical_tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_story_coverage_summaries() -> None:
    if _table_exists("story_coverage_summaries"):
        return

    op.create_table(
        "story_coverage_summaries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("coverage_run_id", sa.Integer(), nullable=False),
        sa.Column("story_id", sa.Integer(), nullable=False),
        sa.Column("coverage_score", sa.Float(), nullable=False),
        sa.Column("status", story_coverage_status, nullable=False),
        sa.Column("matched_symbols", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["coverage_run_id"], ["requirement_coverage_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["story_id"], ["user_stories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def upgrade() -> None:
    _create_required_enums()

    _add_column_if_missing(
        "user_stories",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    _add_column_if_missing(
        "user_stories",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )

    _create_requirement_coverage_runs()
    _add_column_if_missing("requirement_coverage_runs", sa.Column("developer_task_results", sa.JSON(), nullable=True))
    _add_column_if_missing("requirement_coverage_runs", sa.Column("branch", sa.String(), nullable=True))
    _add_column_if_missing("requirement_coverage_runs", sa.Column("commit_sha", sa.String(), nullable=True))
    _add_column_if_missing("requirement_coverage_runs", sa.Column("requirements_snapshot_hash", sa.String(), nullable=True))
    _add_column_if_missing("requirement_coverage_runs", sa.Column("tasks_snapshot_hash", sa.String(), nullable=True))
    _add_column_if_missing("requirement_coverage_runs", sa.Column("assignments_snapshot_hash", sa.String(), nullable=True))
    _create_index_if_missing(
        "ix_requirement_coverage_runs_id",
        "requirement_coverage_runs",
        ["id"],
    )

    _create_code_embedding_records()
    _create_task_embedding_records()
    _create_ac_coverage_results()
    _create_story_coverage_summaries()


def downgrade() -> None:
    op.drop_table("story_coverage_summaries")
    op.drop_table("ac_coverage_results")
    op.drop_table("task_embedding_records")
    op.drop_table("code_embedding_records")
    op.drop_index("ix_requirement_coverage_runs_id", table_name="requirement_coverage_runs")
    op.drop_table("requirement_coverage_runs")
