"""Add confirmation token to user

Revision ID: 20260408_01
Revises: 20260328_01
Create Date: 2026-04-08 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260408_01"
down_revision = "20260328_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user", sa.Column("confirmation_token", sa.String(length=100), nullable=True))
    op.add_column("user", sa.Column("confirmation_token_expiry", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("user", "confirmation_token_expiry")
    op.drop_column("user", "confirmation_token")