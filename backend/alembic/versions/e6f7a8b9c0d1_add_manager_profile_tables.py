"""add manager profile tables

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-06-19 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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

    op.create_table(
        "member_access_permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("manager_id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("can_view_repositories", sa.Boolean(), nullable=False),
        sa.Column("can_run_analysis", sa.Boolean(), nullable=False),
        sa.Column("can_manage_requirements", sa.Boolean(), nullable=False),
        sa.Column("can_view_team_reports", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["manager_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("manager_id", "member_id", name="uq_member_access_permissions_manager_member"),
    )
    op.create_index(op.f("ix_member_access_permissions_id"), "member_access_permissions", ["id"], unique=False)

    op.create_table(
        "profile_activity_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("manager_id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("member_id", sa.Integer(), nullable=True),
        sa.Column("activity_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["manager_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_profile_activity_logs_id"), "profile_activity_logs", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_profile_activity_logs_id"), table_name="profile_activity_logs")
    op.drop_table("profile_activity_logs")
    op.drop_index(op.f("ix_member_access_permissions_id"), table_name="member_access_permissions")
    op.drop_table("member_access_permissions")
    op.drop_index(op.f("ix_manager_team_invites_id"), table_name="manager_team_invites")
    op.drop_index(op.f("ix_manager_team_invites_email"), table_name="manager_team_invites")
    op.drop_table("manager_team_invites")
    op.drop_index(op.f("ix_manager_team_members_id"), table_name="manager_team_members")
    op.drop_table("manager_team_members")
