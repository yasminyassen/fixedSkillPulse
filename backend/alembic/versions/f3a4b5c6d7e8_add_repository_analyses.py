"""add repository_analyses table

Revision ID: f3a4b5c6d7e8
Revises: 82c0c876e130
Create Date: 2026-05-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, None] = "82c0c876e130"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "repository_analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("repository_id", sa.Integer(), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("latest_commit_sha", sa.String(), nullable=True),
        sa.Column("analysis_version", sa.String(), nullable=False),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("analysis_status", sa.String(), nullable=False),
        sa.Column("results_path", sa.String(), nullable=True),
        sa.Column("force_reanalyzed", sa.Boolean(), nullable=True),
        sa.Column("last_run_id", sa.Integer(), sa.ForeignKey("analysis_runs.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_repository_analyses_id", "repository_analyses", ["id"], unique=False)
    op.create_index(
        "uq_repository_analyses_repo_user",
        "repository_analyses",
        ["repository_id", "user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_repository_analyses_repo_user", table_name="repository_analyses")
    op.drop_index("ix_repository_analyses_id", table_name="repository_analyses")
    op.drop_table("repository_analyses")
