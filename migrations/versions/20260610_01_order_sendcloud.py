"""add sendcloud fields to orders

Revision ID: 20260610_01
Revises: 20260609_01
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa

revision = '20260610_01'
down_revision = '20260609_01'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('orders', sa.Column('sendcloud_parcel_id', sa.String(50),  nullable=True))
    op.add_column('orders', sa.Column('label_url',           sa.String(500), nullable=True))


def downgrade():
    op.drop_column('orders', 'label_url')
    op.drop_column('orders', 'sendcloud_parcel_id')
