"""restore shared database revision marker

Revision ID: g1h2i3j4k5l6
Revises: e5f6a7b8c9d0
Create Date: 2026-06-22 00:00:00.000000

This revision intentionally contains no schema operations.

The shared database was stamped at this revision, but this checkout does not
contain the original migration file. Keeping this marker in the graph lets
Alembic resolve the shared database revision and continue using normal
``alembic upgrade head`` commands.
"""

from typing import Sequence, Union


revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
