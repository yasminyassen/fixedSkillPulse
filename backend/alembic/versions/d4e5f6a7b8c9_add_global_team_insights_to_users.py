"""add global team insights to users

Revision ID: d4e5f6a7b8c9
Revises: 48b8e1522e5c
Create Date: 2026-06-17 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "48b8e1522e5c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("global_team_insights", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "global_team_insights")
