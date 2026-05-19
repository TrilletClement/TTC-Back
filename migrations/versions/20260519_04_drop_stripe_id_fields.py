"""Drop stripe_rate_id from shipping_rate and stripe_product_id from board_type

Revision ID: 20260519_04
Revises: 20260519_03
Create Date: 2026-05-19
"""
from alembic import op

revision = '20260519_04'
down_revision = '20260519_03'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('shipping_rate', 'stripe_rate_id')
    op.drop_column('board_type', 'stripe_product_id')


def downgrade():
    import sqlalchemy as sa
    op.add_column('shipping_rate', sa.Column('stripe_rate_id', sa.String(255), nullable=True))
    op.add_column('board_type',    sa.Column('stripe_product_id', sa.String(255), nullable=True))
