"""add location aware attribution fields

Revision ID: i3j4k5l6m7n8
Revises: h1i2j3k4l5m6
Create Date: 2026-06-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "i3j4k5l6m7n8"
down_revision: Union[str, None] =  "j1k2l3m4n5o6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {item["name"] for item in inspector.get_columns(table_name)}
    if column.name not in existing_columns:
        op.add_column(table_name, column)


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {item["name"] for item in inspector.get_columns(table_name)}
    if column_name in existing_columns:
        op.drop_column(table_name, column_name)


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
        _drop_column_if_exists("security_findings", column_name)

    for column_name in ("attributed_contributors", "attribution_source"):
        _drop_column_if_exists("code_metrics", column_name)
