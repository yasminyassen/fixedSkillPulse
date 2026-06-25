"""Add specialization to user

Revision ID: f1b95144f4c8
Revises: 5e27112e4577
Create Date: 2026-05-19 23:47:23.462706

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1b95144f4c8'
down_revision: Union[str, None] = '5e27112e4577'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    sa.Enum('backend', 'frontend', 'qa', name='developerspecialization').create(op.get_bind())
    
    op.add_column('users', sa.Column('specialization', sa.Enum('backend', 'frontend', 'qa', name='developerspecialization'), nullable=True))

def downgrade() -> None:
    op.drop_column('users', 'specialization')

    sa.Enum(name='developerspecialization').drop(op.get_bind())
