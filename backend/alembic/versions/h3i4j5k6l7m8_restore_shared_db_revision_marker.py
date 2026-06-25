"""restore shared database revision marker 3

Revision ID: h3i4j5k6l7m8
Revises: h1i2j3k4l5m6
Create Date: 2026-06-22 00:00:00.000000

This revision intentionally contains no schema operations.

The shared/local database can be stamped at this revision even though the
original migration file is not present in this checkout. Keeping this marker in
the graph lets Alembic resolve the database revision and continue normal
``alembic upgrade head`` commands.
"""

from typing import Sequence, Union


revision: str = "h3i4j5k6l7m8"
down_revision: Union[str, None] = "h1i2j3k4l5m6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
