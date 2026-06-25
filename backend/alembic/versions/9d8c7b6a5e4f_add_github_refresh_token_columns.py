"""add github refresh-token lifecycle columns

Revision ID: 9d8c7b6a5e4f
Revises: b85585449812
Create Date: 2026-04-24 19:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "9d8c7b6a5e4f"
down_revision: Union[str, None] = "b85585449812"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    user_columns = {c["name"] for c in inspector.get_columns("users")}

    if "github_refresh_token" not in user_columns:
        op.add_column("users", sa.Column("github_refresh_token", sa.String(), nullable=True))

    if "github_token_expires_at" not in user_columns:
        op.add_column("users", sa.Column("github_token_expires_at", sa.DateTime(timezone=True), nullable=True))

    if "github_refresh_token_expires_at" not in user_columns:
        op.add_column("users", sa.Column("github_refresh_token_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    user_columns = {c["name"] for c in inspector.get_columns("users")}

    if "github_refresh_token_expires_at" in user_columns:
        op.drop_column("users", "github_refresh_token_expires_at")

    if "github_token_expires_at" in user_columns:
        op.drop_column("users", "github_token_expires_at")

    if "github_refresh_token" in user_columns:
        op.drop_column("users", "github_refresh_token")
