"""merge heads

Revision ID: 82c0c876e130
Revises: 2a6d9f1c8b3e, f2b3c4d5e6f7
Create Date: 2026-05-20 00:24:11.776384

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '82c0c876e130'
down_revision: Union[str, None] = ('2a6d9f1c8b3e', 'f2b3c4d5e6f7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
