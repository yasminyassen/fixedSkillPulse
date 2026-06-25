"""merge_heads

Revision ID: 8670bc648ccd
Revises: 23af8584a322, f3a4b5c6d7e8
Create Date: 2026-05-20 02:18:21.660434

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8670bc648ccd'
down_revision: Union[str, None] = ('23af8584a322', 'f3a4b5c6d7e8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
