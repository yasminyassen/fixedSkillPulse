"""manager profile cleanup

Revision ID: e8b9c0d1e2f3
Revises: e6f7a8b9c0d1
Create Date: 2026-06-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8b9c0d1e2f3"
down_revision: Union[str, None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "profile_activity_logs" in inspector.get_table_names():
        op.execute("DELETE FROM profile_activity_logs WHERE activity_type = 'permissions_updated'")

    if "member_access_permissions" in inspector.get_table_names():
        indexes = {index["name"] for index in inspector.get_indexes("member_access_permissions")}
        if "ix_member_access_permissions_id" in indexes:
            op.drop_index("ix_member_access_permissions_id", table_name="member_access_permissions")
        op.drop_table("member_access_permissions")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "member_access_permissions" in inspector.get_table_names():
        return

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
