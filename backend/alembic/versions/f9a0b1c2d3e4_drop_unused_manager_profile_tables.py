"""drop unused manager profile tables

Revision ID: f9a0b1c2d3e4
Revises: e8b9c0d1e2f3
Create Date: 2026-06-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, None] = "e8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "manager_team_invites" in tables:
        indexes = {index["name"] for index in inspector.get_indexes("manager_team_invites")}
        if "ix_manager_team_invites_id" in indexes:
            op.drop_index("ix_manager_team_invites_id", table_name="manager_team_invites")
        if "ix_manager_team_invites_email" in indexes:
            op.drop_index("ix_manager_team_invites_email", table_name="manager_team_invites")
        op.drop_table("manager_team_invites")

    if "manager_team_members" in tables:
        indexes = {index["name"] for index in inspector.get_indexes("manager_team_members")}
        if "ix_manager_team_members_id" in indexes:
            op.drop_index("ix_manager_team_members_id", table_name="manager_team_members")
        op.drop_table("manager_team_members")


def downgrade() -> None:
    op.create_table(
        "manager_team_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("manager_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["manager_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("manager_id", "user_id", name="uq_manager_team_members_manager_user"),
    )
    op.create_index(op.f("ix_manager_team_members_id"), "manager_team_members", ["id"], unique=False)

    op.create_table(
        "manager_team_invites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("manager_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("specialization", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["manager_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_manager_team_invites_email"), "manager_team_invites", ["email"], unique=False)
    op.create_index(op.f("ix_manager_team_invites_id"), "manager_team_invites", ["id"], unique=False)
