"""add missing security_findings columns

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-03-10 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {c["name"] for c in inspector.get_columns("security_findings")}

    if "tool" not in existing_columns:
        op.add_column('security_findings', sa.Column('tool', sa.String(), nullable=True))
    if "rule" not in existing_columns:
        op.add_column('security_findings', sa.Column('rule', sa.String(), nullable=True))
    if "cwe" not in existing_columns:
        op.add_column('security_findings', sa.Column('cwe', sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {c["name"] for c in inspector.get_columns("security_findings")}

    if "cwe" in existing_columns:
        op.drop_column('security_findings', 'cwe')
    if "rule" in existing_columns:
        op.drop_column('security_findings', 'rule')
    if "tool" in existing_columns:
        op.drop_column('security_findings', 'tool')
