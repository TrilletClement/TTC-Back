"""Add newsletter_subscriber table.

Revision ID: 20260916_01
Revises: 20260902_01
Create Date: 2026-09-16
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260916_01"
down_revision: Union[str, None] = "20260902_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "newsletter_subscriber",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=120), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("unsubscribe_token", sa.String(length=100), nullable=False),
        sa.Column("subscribed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_newsletter_subscriber_email", "newsletter_subscriber", ["email"], unique=True)
    op.create_unique_constraint(
        "uq_newsletter_subscriber_unsubscribe_token", "newsletter_subscriber", ["unsubscribe_token"]
    )


def downgrade() -> None:
    op.drop_index("ix_newsletter_subscriber_email", table_name="newsletter_subscriber")
    op.drop_table("newsletter_subscriber")
