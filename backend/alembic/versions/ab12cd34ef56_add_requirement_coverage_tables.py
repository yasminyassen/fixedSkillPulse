"""add requirement coverage tables

Revision ID: ab12cd34ef56
Revises: f4a5b6c7d8e9
Create Date: 2026-06-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ab12cd34ef56"
down_revision: Union[str, None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE documentstatus ADD VALUE IF NOT EXISTS 'confirmed'")

    op.create_table(
        "requirement_coverage_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("analysis_run_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "running", "completed", "failed", name="coveragerunstatus"),
            nullable=False,
        ),
        sa.Column("overall_coverage", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("discovery_links", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["requirement_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_requirement_coverage_runs_id", "requirement_coverage_runs", ["id"])

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

    op.create_table(
        "ac_coverage_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("coverage_run_id", sa.Integer(), nullable=False),
        sa.Column("story_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("ac_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("COVERED", "PARTIALLY_COVERED", "NOT_COVERED", name="accoveragestatus"),
            nullable=False,
        ),
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

    op.create_table(
        "story_coverage_summaries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("coverage_run_id", sa.Integer(), nullable=False),
        sa.Column("story_id", sa.Integer(), nullable=False),
        sa.Column("coverage_score", sa.Float(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("implemented", "partially_implemented", "not_implemented", name="storycoveragestatus"),
            nullable=False,
        ),
        sa.Column("matched_symbols", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["coverage_run_id"], ["requirement_coverage_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["story_id"], ["user_stories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("story_coverage_summaries")
    op.drop_table("ac_coverage_results")
    op.drop_table("task_embedding_records")
    op.drop_table("code_embedding_records")
    op.drop_index("ix_requirement_coverage_runs_id", table_name="requirement_coverage_runs")
    op.drop_table("requirement_coverage_runs")
    op.execute("DROP TYPE IF EXISTS storycoveragestatus")
    op.execute("DROP TYPE IF EXISTS accoveragestatus")
    op.execute("DROP TYPE IF EXISTS coveragerunstatus")
