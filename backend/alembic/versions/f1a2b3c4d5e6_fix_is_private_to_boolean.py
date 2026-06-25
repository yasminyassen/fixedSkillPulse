"""fix is_private to boolean

Revision ID: f1a2b3c4d5e6
Revises: dc7d5e8d240d
Create Date: 2026-03-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'dc7d5e8d240d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'repositories',
        'is_private',
        type_=sa.Boolean(),
        existing_type=sa.Integer(),
        postgresql_using='is_private::boolean',
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'repositories',
        'is_private',
        type_=sa.Integer(),
        existing_type=sa.Boolean(),
        postgresql_using='is_private::integer',
        nullable=True,
    )
