"""add sonar analysis tables

Revision ID: j1k2l3m4n5o6
Revises: i1j2k3l4m5n6
Create Date: 2026-06-23 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "j1k2l3m4n5o6"
down_revision = "i1j2k3l4m5n6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sonar_analysis_summaries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("analysis_run_id", sa.Integer(), sa.ForeignKey("analysis_runs.id"), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("project_key", sa.String(), nullable=True),
        sa.Column("quality_gate", sa.String(), nullable=True),
        sa.Column("sonar_health_score", sa.Float(), nullable=True),
        sa.Column("measures", sa.JSON(), nullable=True),
        sa.Column("coverage", sa.JSON(), nullable=True),
        sa.Column("scanner", sa.JSON(), nullable=True),
        sa.Column("ce_task", sa.JSON(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_sonar_analysis_summaries_id", "sonar_analysis_summaries", ["id"])
    op.create_index("ix_sonar_analysis_summaries_analysis_run_id", "sonar_analysis_summaries", ["analysis_run_id"])

    op.create_table(
        "sonar_file_measures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("analysis_run_id", sa.Integer(), sa.ForeignKey("analysis_runs.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("measures", sa.JSON(), nullable=True),
        sa.Column("coverage", sa.Float(), nullable=True),
        sa.Column("duplicated_lines", sa.Float(), nullable=True),
        sa.Column("duplicated_lines_density", sa.Float(), nullable=True),
        sa.Column("ncloc", sa.Float(), nullable=True),
        sa.Column("complexity", sa.Float(), nullable=True),
        sa.Column("cognitive_complexity", sa.Float(), nullable=True),
        sa.Column("functions", sa.Float(), nullable=True),
        sa.Column("classes", sa.Float(), nullable=True),
        sa.Column("statements", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_sonar_file_measures_id", "sonar_file_measures", ["id"])
    op.create_index("ix_sonar_file_measures_analysis_run_id", "sonar_file_measures", ["analysis_run_id"])

    op.create_table(
        "sonar_issues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("analysis_run_id", sa.Integer(), sa.ForeignKey("analysis_runs.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("issue_key", sa.String(), nullable=True),
        sa.Column("file_path", sa.String(), nullable=True),
        sa.Column("line", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(), nullable=True),
        sa.Column("severity", sa.String(), nullable=True),
        sa.Column("rule", sa.String(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("raw_issue", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_sonar_issues_id", "sonar_issues", ["id"])
    op.create_index("ix_sonar_issues_analysis_run_id", "sonar_issues", ["analysis_run_id"])


def downgrade() -> None:
    op.drop_index("ix_sonar_issues_analysis_run_id", table_name="sonar_issues")
    op.drop_index("ix_sonar_issues_id", table_name="sonar_issues")
    op.drop_table("sonar_issues")

    op.drop_index("ix_sonar_file_measures_analysis_run_id", table_name="sonar_file_measures")
    op.drop_index("ix_sonar_file_measures_id", table_name="sonar_file_measures")
    op.drop_table("sonar_file_measures")

    op.drop_index("ix_sonar_analysis_summaries_analysis_run_id", table_name="sonar_analysis_summaries")
    op.drop_index("ix_sonar_analysis_summaries_id", table_name="sonar_analysis_summaries")
    op.drop_table("sonar_analysis_summaries")
