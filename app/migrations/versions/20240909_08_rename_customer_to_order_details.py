"""Rename customer to order_details and add user link

Revision ID: 20240909_08
Revises: 20240909_07
Create Date: 2024-09-09 00:00:08.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20240909_08'
down_revision = '20240909_07'
branch_labels = None
depends_on = None


def upgrade():
    # Rename table customer -> order_details
    op.rename_table('customer', 'order_details')

    # Add user_id column
    op.add_column('order_details', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_order_details_user', 'order_details', 'user', ['user_id'], ['id'], ondelete='SET NULL')

    # Rename order.customer_id -> order_details_id and update FK
    with op.batch_alter_table('order') as batch_op:
        batch_op.alter_column('customer_id', new_column_name='order_details_id')
        batch_op.drop_constraint('fk_order_customer', type_='foreignkey')
        batch_op.create_foreign_key('fk_order_order_details', 'order_details', ['order_details_id'], ['id'], ondelete='SET NULL')


def downgrade():
    # Revert order FK/column
    with op.batch_alter_table('order') as batch_op:
        batch_op.drop_constraint('fk_order_order_details', type_='foreignkey')
        batch_op.alter_column('order_details_id', new_column_name='customer_id')
        batch_op.create_foreign_key('fk_order_customer', 'customer', ['customer_id'], ['id'], ondelete='SET NULL')

    # Drop user_id FK/column
    op.drop_constraint('fk_order_details_user', 'order_details', type_='foreignkey')
    op.drop_column('order_details', 'user_id')

    # Rename table back
    op.rename_table('order_details', 'customer')
