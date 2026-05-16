"""add_address_type_phone_billing

- order_details: add `type` (shipping|billing) and `phone`
- orders: add `billing_details_id` FK to support a separate billing address

Revision ID: 20260516_04
Revises: 20260516_03
Create Date: 2026-05-16

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '20260516_04'
down_revision: Union[str, None] = '20260516_03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('order_details', sa.Column('type',  sa.String(20),  nullable=False, server_default='shipping'))
    op.add_column('order_details', sa.Column('phone', sa.String(30),  nullable=True))

    op.add_column(
        'orders',
        sa.Column('billing_details_id', sa.Integer(), sa.ForeignKey('order_details.id'), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('orders', 'billing_details_id')
    op.drop_column('order_details', 'phone')
    op.drop_column('order_details', 'type')
