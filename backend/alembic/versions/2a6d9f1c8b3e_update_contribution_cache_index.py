"""update contribution cache index

Revision ID: 2a6d9f1c8b3e
Revises: 7f4a9c2d1e8b
Create Date: 2026-04-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "2a6d9f1c8b3e"
down_revision: Union[str, None] = "7f4a9c2d1e8b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.drop_index("ix_analysis_runs_contribution_cache", table_name="analysis_runs")
    op.create_index(
        "ix_analysis_runs_contribution_cache",
        "analysis_runs",
        ["repository_id", "branch", "commit_sha", "analysis_scope", "status"],
    )


def downgrade():
    op.drop_index("ix_analysis_runs_contribution_cache", table_name="analysis_runs")
    op.create_index(
        "ix_analysis_runs_contribution_cache",
        "analysis_runs",
        ["repository_id", "branch", "commit_sha", "analysis_scope", "contributor_login", "status"],
    )
