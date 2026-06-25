"""repair security attribution columns

Revision ID: l1m2n3o4p5q6
Revises: k1l2m3n4o5p6
Create Date: 2026-06-24 00:00:00.000000

The shared database was stamped past the attribution migration without all of
its columns. Add the current model columns if they are missing.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "l1m2n3o4p5q6"
down_revision: Union[str, None] = "k1l2m3n4o5p6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return column_name in {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if _table_exists(table_name) and not _column_exists(table_name, column.name):
        op.add_column(table_name, column)


def upgrade() -> None:
    _add_column_if_missing("security_findings", sa.Column("start_line", sa.Integer(), nullable=True))
    _add_column_if_missing("security_findings", sa.Column("end_line", sa.Integer(), nullable=True))
    _add_column_if_missing("security_findings", sa.Column("start_column", sa.Integer(), nullable=True))
    _add_column_if_missing("security_findings", sa.Column("end_column", sa.Integer(), nullable=True))
    _add_column_if_missing("security_findings", sa.Column("package_name", sa.String(), nullable=True))
    _add_column_if_missing("security_findings", sa.Column("package_version", sa.String(), nullable=True))
    _add_column_if_missing("security_findings", sa.Column("manifest_file", sa.String(), nullable=True))
    _add_column_if_missing("security_findings", sa.Column("vulnerability_id", sa.String(), nullable=True))
    _add_column_if_missing("security_findings", sa.Column("advisory_id", sa.String(), nullable=True))
    _add_column_if_missing("security_findings", sa.Column("raw_metadata", sa.JSON(), nullable=True))
    _add_column_if_missing("security_findings", sa.Column("attribution_source", sa.String(), nullable=True))
    _add_column_if_missing("security_findings", sa.Column("attributed_contributors", sa.JSON(), nullable=True))

    _add_column_if_missing("code_metrics", sa.Column("attribution_source", sa.String(), nullable=True))
    _add_column_if_missing("code_metrics", sa.Column("attributed_contributors", sa.JSON(), nullable=True))


def downgrade() -> None:
    for column_name in (
        "attributed_contributors",
        "attribution_source",
        "raw_metadata",
        "advisory_id",
        "vulnerability_id",
        "manifest_file",
        "package_version",
        "package_name",
        "end_column",
        "start_column",
        "end_line",
        "start_line",
    ):
        if _column_exists("security_findings", column_name):
            op.drop_column("security_findings", column_name)

    for column_name in ("attributed_contributors", "attribution_source"):
        if _column_exists("code_metrics", column_name):
            op.drop_column("code_metrics", column_name)
