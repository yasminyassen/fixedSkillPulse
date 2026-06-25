"""add contributor analysis summaries

Revision ID: m1n2o3p4q5r6
Revises: l1m2n3o4p5q6
Create Date: 2026-06-25 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "m1n2o3p4q5r6"
down_revision: Union[str, None] = "l1m2n3o4p5q6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contributor_analysis_summaries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("analysis_run_id", sa.Integer(), sa.ForeignKey("analysis_runs.id"), nullable=False),
        sa.Column("repository_id", sa.Integer(), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("contributor_login", sa.String(), nullable=True),
        sa.Column("files_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("touched_files", sa.JSON(), nullable=True),
        sa.Column("skill_score", sa.Float(), nullable=True),
        sa.Column("sonar_health_score", sa.Float(), nullable=True),
        sa.Column("security_score", sa.Float(), nullable=True),
        sa.Column("coverage", sa.Float(), nullable=True),
        sa.Column("bugs", sa.Integer(), nullable=True),
        sa.Column("code_smells", sa.Integer(), nullable=True),
        sa.Column("duplicated_lines", sa.Float(), nullable=True),
        sa.Column("duplicated_lines_density", sa.Float(), nullable=True),
        sa.Column("complexity", sa.Float(), nullable=True),
        sa.Column("cognitive_complexity", sa.Float(), nullable=True),
        sa.Column("ncloc", sa.Float(), nullable=True),
        sa.Column("quality_gate", sa.String(), nullable=True),
        sa.Column("measures", sa.JSON(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "analysis_run_id",
            "user_id",
            name="uq_contributor_analysis_summary_run_user",
        ),
    )
    op.create_index("ix_contributor_analysis_summaries_id", "contributor_analysis_summaries", ["id"])
    op.create_index(
        "ix_contributor_analysis_summaries_analysis_run_id",
        "contributor_analysis_summaries",
        ["analysis_run_id"],
    )
    op.create_index(
        "ix_contributor_analysis_summaries_repository_id",
        "contributor_analysis_summaries",
        ["repository_id"],
    )
    op.create_index(
        "ix_contributor_analysis_summaries_user_id",
        "contributor_analysis_summaries",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_contributor_analysis_summaries_user_id", table_name="contributor_analysis_summaries")
    op.drop_index("ix_contributor_analysis_summaries_repository_id", table_name="contributor_analysis_summaries")
    op.drop_index("ix_contributor_analysis_summaries_analysis_run_id", table_name="contributor_analysis_summaries")
    op.drop_index("ix_contributor_analysis_summaries_id", table_name="contributor_analysis_summaries")
    op.drop_table("contributor_analysis_summaries")
