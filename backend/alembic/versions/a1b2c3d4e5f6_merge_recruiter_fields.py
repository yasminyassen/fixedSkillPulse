"""merge recruiter fields

Revision ID: a1b2c3d4e5f6
Revises: 8670bc648ccd, 9caea9779afb
Create Date: 2026-05-25 00:39:00.369036

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, tuple[str, str], None] = ('8670bc648ccd', '9caea9779afb')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass