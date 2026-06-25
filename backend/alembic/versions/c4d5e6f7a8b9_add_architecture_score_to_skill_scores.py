"""add architecture_score to skill_scores

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-04-17 22:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {c["name"] for c in inspector.get_columns("skill_scores")}

    if "architecture_score" not in existing_columns:
        op.add_column(
            "skill_scores",
            sa.Column("architecture_score", sa.Float(), nullable=True),
        )

    # Backfill architecture_score from legacy security_awareness_score if present.
    if "security_awareness_score" in existing_columns:
        op.execute(
            """
            UPDATE skill_scores
            SET architecture_score = security_awareness_score
            WHERE architecture_score IS NULL
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {c["name"] for c in inspector.get_columns("skill_scores")}

    if "architecture_score" in existing_columns:
        op.drop_column("skill_scores", "architecture_score")
