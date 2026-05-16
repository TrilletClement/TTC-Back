"""refactor_order_details_and_orders

- order_details: drop `type` column (role is implied by FK name on orders)
- orders: rename `order_details_id` -> `shipping_details_id`
- orders: drop `led_colors` column
- orders: backfill billing_details_id = shipping_details_id where NULL (same address)

Revision ID: 20260516_05
Revises: 20260516_04
Create Date: 2026-05-16

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '20260516_05'
down_revision: Union[str, None] = '20260516_04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('order_details', 'type')

    op.alter_column('orders', 'order_details_id', new_column_name='shipping_details_id')

    op.drop_column('orders', 'led_colors')

    op.execute(sa.text(
        "UPDATE orders SET billing_details_id = shipping_details_id WHERE billing_details_id IS NULL"
    ))


def downgrade() -> None:
    op.add_column('orders', sa.Column('led_colors', sa.String(255), nullable=True))
    op.alter_column('orders', 'shipping_details_id', new_column_name='order_details_id')
    op.add_column('order_details', sa.Column('type', sa.String(20), nullable=False, server_default='shipping'))
