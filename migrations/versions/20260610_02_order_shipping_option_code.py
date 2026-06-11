"""add shipping_option_code to orders

Revision ID: 20260610_02
Revises: 20260610_01
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa

revision = '20260610_02'
down_revision = '20260610_01'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('orders', sa.Column('shipping_option_code', sa.String(100), nullable=True))


def downgrade():
    op.drop_column('orders', 'shipping_option_code')
