"""add contribution scope to analysis runs

Revision ID: 7f4a9c2d1e8b
Revises: 5d0ed1733c3c
Create Date: 2026-04-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7f4a9c2d1e8b"
down_revision: Union[str, None] = "5d0ed1733c3c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        "analysis_runs",
        sa.Column("analysis_scope", sa.String(), nullable=True, server_default="repository"),
    )
    op.add_column(
        "analysis_runs",
        sa.Column("contributor_login", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_analysis_runs_contribution_cache",
        "analysis_runs",
        ["repository_id", "branch", "commit_sha", "analysis_scope", "status"],
    )


def downgrade():
    op.drop_index("ix_analysis_runs_contribution_cache", table_name="analysis_runs")
    op.drop_column("analysis_runs", "contributor_login")
    op.drop_column("analysis_runs", "analysis_scope")
