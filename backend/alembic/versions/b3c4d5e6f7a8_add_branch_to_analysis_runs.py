"""add branch to analysis_runs

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-04-17 21:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {c["name"] for c in inspector.get_columns("analysis_runs")}

    if "branch" not in existing_columns:
        op.add_column(
            "analysis_runs",
            sa.Column("branch", sa.String(), nullable=True, server_default="main"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {c["name"] for c in inspector.get_columns("analysis_runs")}

    if "branch" in existing_columns:
        op.drop_column("analysis_runs", "branch")
