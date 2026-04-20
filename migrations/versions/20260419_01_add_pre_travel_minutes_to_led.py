"""Add pre_travel_minutes to led

Revision ID: 20260419_01
Revises: 20260408_01
Create Date: 2026-04-19 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260419_01"
down_revision = "20260408_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("led", sa.Column("pre_travel_minutes", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("led", "pre_travel_minutes")