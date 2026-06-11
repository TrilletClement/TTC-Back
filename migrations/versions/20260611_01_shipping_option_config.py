"""add shipping_option_config table

Revision ID: 20260611_01
Revises: 20260610_03
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa

revision = '20260611_01'
down_revision = '20260610_03'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'shipping_option_config',
        sa.Column('id',            sa.Integer,     primary_key=True),
        sa.Column('option_code',   sa.String(100), unique=True, nullable=False),
        sa.Column('enabled',       sa.Boolean,     nullable=False, server_default='true'),
        sa.Column('countries',     sa.JSON,        nullable=True),
        sa.Column('display_order', sa.Integer,     nullable=False, server_default='0'),
    )


def downgrade():
    op.drop_table('shipping_option_config')
