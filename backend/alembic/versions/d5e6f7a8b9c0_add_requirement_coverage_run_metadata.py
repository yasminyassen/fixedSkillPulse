"""add requirement coverage run metadata

Revision ID: d5e6f7a8b9c0
Revises: ab12cd34ef56
Create Date: 2026-06-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "ab12cd34ef56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_stories", sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))
    op.add_column("user_stories", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))
    op.add_column("requirement_coverage_runs", sa.Column("branch", sa.String(), nullable=True))
    op.add_column("requirement_coverage_runs", sa.Column("commit_sha", sa.String(), nullable=True))
    op.add_column("requirement_coverage_runs", sa.Column("requirements_snapshot_hash", sa.String(), nullable=True))
    op.add_column("requirement_coverage_runs", sa.Column("tasks_snapshot_hash", sa.String(), nullable=True))
    op.add_column("requirement_coverage_runs", sa.Column("assignments_snapshot_hash", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("requirement_coverage_runs", "assignments_snapshot_hash")
    op.drop_column("requirement_coverage_runs", "tasks_snapshot_hash")
    op.drop_column("requirement_coverage_runs", "requirements_snapshot_hash")
    op.drop_column("requirement_coverage_runs", "commit_sha")
    op.drop_column("requirement_coverage_runs", "branch")
    op.drop_column("user_stories", "updated_at")
    op.drop_column("user_stories", "created_at")
