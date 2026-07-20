"""add sendcloud_shipment_id and return_requested_at to orders

Revision ID: 20260720_04
Revises: 20260720_03
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa

revision = '20260720_04'
down_revision = '20260720_03'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('orders', sa.Column('sendcloud_shipment_id', sa.String(50), nullable=True))
    op.add_column('orders', sa.Column('return_requested_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('orders', 'return_requested_at')
    op.drop_column('orders', 'sendcloud_shipment_id')
