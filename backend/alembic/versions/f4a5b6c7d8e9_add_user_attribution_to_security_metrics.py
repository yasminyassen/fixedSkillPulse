"""add user attribution to security metrics

Revision ID: f4a5b6c7d8e9
Revises: a0b1c2d3e4f5
Create Date: 2026-06-21 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, None] = "a0b1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("code_metrics", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_code_metrics_user_id_users",
        "code_metrics",
        "users",
        ["user_id"],
        ["id"],
    )
    op.create_index("ix_code_metrics_user_id", "code_metrics", ["user_id"])

    op.add_column("security_findings", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_security_findings_user_id_users",
        "security_findings",
        "users",
        ["user_id"],
        ["id"],
    )
    op.create_index("ix_security_findings_user_id", "security_findings", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_security_findings_user_id", table_name="security_findings")
    op.drop_constraint("fk_security_findings_user_id_users", "security_findings", type_="foreignkey")
    op.drop_column("security_findings", "user_id")

    op.drop_index("ix_code_metrics_user_id", table_name="code_metrics")
    op.drop_constraint("fk_code_metrics_user_id_users", "code_metrics", type_="foreignkey")
    op.drop_column("code_metrics", "user_id")
