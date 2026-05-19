"""Add shipping_rate table linked to price_version

Revision ID: 20260519_03
Revises: 20260519_02
Create Date: 2026-05-19
"""
from alembic import op
import sqlalchemy as sa

revision = '20260519_03'
down_revision = '20260519_02'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'shipping_rate',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('price_version_id', sa.Integer(), sa.ForeignKey('price_version.id', ondelete='CASCADE'), nullable=False),
        sa.Column('country_code', sa.String(3), nullable=False),
        sa.Column('country_name', sa.String(100), nullable=False),
        sa.Column('cost_cents', sa.Integer(), nullable=False),
        sa.Column('delivery_days_min', sa.Integer(), nullable=False),
        sa.Column('delivery_days_max', sa.Integer(), nullable=False),
        sa.Column('stripe_rate_id', sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('price_version_id', 'country_code', name='uq_shipping_version_country'),
    )
    op.create_index('ix_shipping_rate_version', 'shipping_rate', ['price_version_id'])


def downgrade():
    op.drop_index('ix_shipping_rate_version', table_name='shipping_rate')
    op.drop_table('shipping_rate')
