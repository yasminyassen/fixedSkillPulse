"""add recruiter_candidates table

Revision ID: f2b3c4d5e6f7
Revises: b85585449812
Create Date: 2026-05-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f2b3c4d5e6f7"
down_revision: Union[str, None] = "b85585449812"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recruiter_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("analysis_run_id", sa.Integer(), sa.ForeignKey("analysis_runs.id"), nullable=False, unique=True),
        sa.Column("candidate_name", sa.String(), nullable=False),
        sa.Column("github_login", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_recruiter_candidates_id", "recruiter_candidates", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_recruiter_candidates_id", table_name="recruiter_candidates")
    op.drop_table("recruiter_candidates")
