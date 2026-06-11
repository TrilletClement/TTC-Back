"""drop shipping_rate, drop countries col, add shipping_country

Revision ID: 20260611_02
Revises: 20260611_01
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa

revision = '20260611_02'
down_revision = '20260611_01'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table('shipping_rate')
    op.drop_column('shipping_option_config', 'countries')
    op.create_table(
        'shipping_country',
        sa.Column('id',           sa.Integer,    primary_key=True),
        sa.Column('country_code', sa.String(3),  unique=True, nullable=False),
        sa.Column('sort_order',   sa.Integer,    nullable=False, server_default='0'),
    )


def downgrade():
    op.drop_table('shipping_country')
    op.add_column('shipping_option_config',
        sa.Column('countries', sa.JSON, nullable=True))
    op.create_table(
        'shipping_rate',
        sa.Column('id',               sa.Integer,     primary_key=True),
        sa.Column('price_version_id', sa.Integer,     sa.ForeignKey('price_version.id', ondelete='CASCADE'), nullable=False),
        sa.Column('country_code',     sa.String(3),   nullable=False),
        sa.Column('country_name',     sa.String(100), nullable=False),
        sa.Column('cost_cents',       sa.Integer,     nullable=False),
        sa.Column('delivery_days_min',sa.Integer,     nullable=False),
        sa.Column('delivery_days_max',sa.Integer,     nullable=False),
    )
