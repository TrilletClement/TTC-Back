"""Add customer table and link orders

Revision ID: 20240909_07
Revises: 20240909_06
Create Date: 2024-09-09 00:00:07.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20240909_07'
down_revision = '20240909_06'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'customer',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('first_name', sa.String(length=100), nullable=True),
        sa.Column('last_name', sa.String(length=100), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True, unique=True),
        sa.Column('address_line1', sa.String(length=255), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=True),
        sa.Column('postal_code', sa.String(length=20), nullable=True),
        sa.Column('country', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False)
    )

    op.add_column('order', sa.Column('customer_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_order_customer', 'order', 'customer', ['customer_id'], ['id'], ondelete='SET NULL')


def downgrade():
    op.drop_constraint('fk_order_customer', 'order', type_='foreignkey')
    op.drop_column('order', 'customer_id')
    op.drop_table('customer')
