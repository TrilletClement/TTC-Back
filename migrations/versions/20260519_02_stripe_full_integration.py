"""Stripe full integration

- board_type: add stripe_product_id (nullable) for analytics / line-item naming
- orders: add cart_ref (customer-facing ref), payment_intent_id (for refunds),
          shipping_cost_cents (populated from Stripe webhook)
- orders: make shipping_details_id explicitly nullable (populated by webhook now)

Revision ID: 20260519_02
Revises: 20260519_01
Create Date: 2026-05-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '20260519_02'
down_revision: Union[str, None] = '20260519_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('board_type', sa.Column('stripe_product_id', sa.String(255), nullable=True))

    op.add_column('orders', sa.Column('cart_ref',           sa.String(20),  nullable=True))
    op.add_column('orders', sa.Column('payment_intent_id',  sa.String(255), nullable=True))
    op.add_column('orders', sa.Column('shipping_cost_cents', sa.Integer(),   nullable=True))

    op.alter_column('orders', 'shipping_details_id', existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.alter_column('orders', 'shipping_details_id', existing_type=sa.Integer(), nullable=False)

    op.drop_column('orders', 'shipping_cost_cents')
    op.drop_column('orders', 'payment_intent_id')
    op.drop_column('orders', 'cart_ref')

    op.drop_column('board_type', 'stripe_product_id')
