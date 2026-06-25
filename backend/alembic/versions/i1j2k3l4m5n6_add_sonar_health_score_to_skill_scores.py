"""add sonar_health_score to skill_scores

Revision ID: i1j2k3l4m5n6
Revises: h3i4j5k6l7m8
Create Date: 2026-06-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "i1j2k3l4m5n6"
down_revision = "h3i4j5k6l7m8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("skill_scores")}
    if "sonar_health_score" not in existing_columns:
        op.add_column("skill_scores", sa.Column("sonar_health_score", sa.Float(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("skill_scores")}
    if "sonar_health_score" in existing_columns:
        op.drop_column("skill_scores", "sonar_health_score")
