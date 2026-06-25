"""add developer task coverage results

Revision ID: e5f6a7b8c9d0
Revises: d5e6f7a8b9c0
Create Date: 2026-06-20 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("requirement_coverage_runs", sa.Column("developer_task_results", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("requirement_coverage_runs", "developer_task_results")
