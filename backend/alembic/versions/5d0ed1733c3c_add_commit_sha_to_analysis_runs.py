"""add commit_sha to analysis_runs

Revision ID: 5d0ed1733c3c
Revises: 9d8c7b6a5e4f
Create Date: 2026-04-25 08:38:39.393676

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d0ed1733c3c'
down_revision: Union[str, None] = '9d8c7b6a5e4f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        'analysis_runs',
        sa.Column('commit_sha', sa.String(length=40), nullable=True)
    )

    op.create_index(
        'ix_analysis_runs_commit_sha',
        'analysis_runs',
        ['repository_id', 'branch', 'commit_sha', 'status']
    )


def downgrade():
    op.drop_index('ix_analysis_runs_commit_sha', table_name='analysis_runs')
    op.drop_column('analysis_runs', 'commit_sha')