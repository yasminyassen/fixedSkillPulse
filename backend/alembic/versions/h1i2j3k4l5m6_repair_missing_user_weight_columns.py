"""repair missing user weight columns

Revision ID: h1i2j3k4l5m6
Revises: h2i3j4k5l6m7
Create Date: 2026-06-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h1i2j3k4l5m6"
down_revision: Union[str, None] = "h2i3j4k5l6m7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TABLE users ADD COLUMN IF NOT EXISTS weight_architecture INTEGER"))
    op.execute(sa.text("ALTER TABLE users ADD COLUMN IF NOT EXISTS weight_maintainability INTEGER"))
    op.execute(sa.text("ALTER TABLE users ADD COLUMN IF NOT EXISTS global_team_insights JSON"))
    op.execute(sa.text("UPDATE users SET weight_architecture = 20 WHERE weight_architecture IS NULL"))
    op.execute(sa.text("UPDATE users SET weight_maintainability = 20 WHERE weight_maintainability IS NULL"))


def downgrade() -> None:
    op.drop_column("users", "global_team_insights")
    op.drop_column("users", "weight_maintainability")
    op.drop_column("users", "weight_architecture")
