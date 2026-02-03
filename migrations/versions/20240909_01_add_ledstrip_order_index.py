"""Add order_index to led_strip

Revision ID: 20240909_01
Revises: 
Create Date: 2024-09-09
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20240909_01'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('led_strip', sa.Column('order_index', sa.Integer(), nullable=True, server_default='1'))

    bind = op.get_bind()
    metadata = sa.MetaData()
    metadata.bind = bind

    led_strip = sa.Table('led_strip', metadata, autoload_with=bind)

    # Fetch strips grouped by board and ordered by id
    rows = bind.execute(
        sa.select(
            led_strip.c.id,
            led_strip.c.board_id
        ).order_by(led_strip.c.board_id, led_strip.c.id)
    ).fetchall()

    current_board = None
    counter = 0
    updates = []
    for row in rows:
        if row.board_id != current_board:
            current_board = row.board_id
            counter = 1
        else:
            counter += 1
        updates.append({'id': row.id, 'order_index': counter})

    for upd in updates:
        op.execute(
            led_strip.update()
            .where(led_strip.c.id == upd['id'])
            .values(order_index=upd['order_index'])
        )

    op.alter_column('led_strip', 'order_index', nullable=False, server_default='1')


def downgrade():
    op.drop_column('led_strip', 'order_index')
