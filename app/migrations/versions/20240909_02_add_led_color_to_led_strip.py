"""Add led_color to led_strip

Revision ID: 20240909_02
Revises: 20240909_01
Create Date: 2024-09-09
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20240909_02'
down_revision = '20240909_01'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('led_strip', sa.Column('led_color', sa.String(length=50), nullable=True, server_default='red'))

    led_strip = sa.table(
        'led_strip',
        sa.column('id', sa.Integer),
        sa.column('led_color', sa.String)
    )

    op.execute(
        led_strip.update().values(led_color='red')
    )

    op.alter_column('led_strip', 'led_color', nullable=False, server_default='red')


def downgrade():
    op.drop_column('led_strip', 'led_color')
