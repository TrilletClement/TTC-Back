"""Drop legacy details column from order

Revision ID: 20240909_09
Revises: 20240909_08
Create Date: 2024-09-09 00:00:09.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20240909_09'
down_revision = '20240909_08'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('order') as batch_op:
        batch_op.drop_column('details')


def downgrade():
    with op.batch_alter_table('order') as batch_op:
        batch_op.add_column(sa.Column('details', sa.String(length=500), nullable=True))
