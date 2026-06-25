"""add recruiter architecture and maintainability weights

Revision ID: a0b1c2d3e4f5
Revises: f9a0b1c2d3e4
Create Date: 2026-06-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a0b1c2d3e4f5"
down_revision: Union[str, None] = "f9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TABLE users ADD COLUMN IF NOT EXISTS weight_architecture INTEGER"))
    op.execute(sa.text("ALTER TABLE users ADD COLUMN IF NOT EXISTS weight_maintainability INTEGER"))
    op.execute(sa.text("UPDATE users SET weight_architecture = 20 WHERE weight_architecture IS NULL"))
    op.execute(sa.text("UPDATE users SET weight_maintainability = 20 WHERE weight_maintainability IS NULL"))


def downgrade() -> None:
    op.drop_column("users", "weight_maintainability")
    op.drop_column("users", "weight_architecture")
