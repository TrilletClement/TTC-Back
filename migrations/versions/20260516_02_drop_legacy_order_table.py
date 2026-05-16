"""drop_legacy_order_table

The 'order' table was the original order table (created in 20240909_03).
It has been fully replaced by the 'orders' table, which adds Stripe fields
(stripe_session_id, user_id, amount_cents, currency, paid_at) and is what
the ORM model and all services now target.

Revision ID: 20260516_02
Revises: 20260516_01
Create Date: 2026-05-16

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '20260516_02'
down_revision: Union[str, None] = '20260516_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('order')


def downgrade() -> None:
    op.create_table(
        'order',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('board_id', sa.Integer(), sa.ForeignKey('board.id'), nullable=False),
        sa.Column('svg_path', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('led_colors', sa.String(length=255), nullable=True),
        sa.Column('order_details_id', sa.Integer(), sa.ForeignKey('order_details.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
