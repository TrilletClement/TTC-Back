"""split order into order + order_item

Revision ID: 20260613_01
Revises: 20260611_03
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa

revision = '20260613_01'
down_revision = '20260611_03'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create order_item table
    op.create_table(
        'order_item',
        sa.Column('id',            sa.Integer(),  nullable=False, autoincrement=True),
        sa.Column('order_id',      sa.Integer(),  nullable=False),
        sa.Column('board_id',      sa.Integer(),  nullable=True),
        sa.Column('svg_content',   sa.Text(),     nullable=True),
        sa.Column('amount_cents',  sa.Integer(),  nullable=False, server_default='0'),
        sa.Column('esp_device_id', sa.Integer(),  nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['order_id'],      ['orders.id'],      ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['board_id'],      ['board.id']),
        sa.ForeignKeyConstraint(['esp_device_id'], ['esp32_device.id']),
    )

    # 2. For each existing order row, create an order_item pointing to the
    #    canonical order for that cart_ref (min id in group, or self for no cart_ref).
    op.execute("""
        INSERT INTO order_item (order_id, board_id, svg_content, amount_cents, esp_device_id)
        SELECT
            COALESCE(
                (SELECT MIN(o2.id)
                 FROM orders o2
                 WHERE o2.cart_ref = o.cart_ref
                   AND o.cart_ref IS NOT NULL),
                o.id
            ) AS order_id,
            o.board_id,
            o.svg_content,
            o.amount_cents,
            o.esp_device_id
        FROM orders o
    """)

    # 3. Set amount_cents on canonical orders to sum of their items' prices
    op.execute("""
        UPDATE orders
        SET amount_cents = (
            SELECT COALESCE(SUM(oi.amount_cents), 0)
            FROM order_item oi
            WHERE oi.order_id = orders.id
        )
    """)

    # 4. Delete non-canonical orders (duplicates within same cart_ref group)
    op.execute("""
        DELETE FROM orders
        WHERE cart_ref IS NOT NULL
          AND id != (
              SELECT MIN(id)
              FROM orders o2
              WHERE o2.cart_ref = orders.cart_ref
          )
    """)

    # 5. Drop the columns that moved to order_item
    op.drop_column('orders', 'board_id')
    op.drop_column('orders', 'svg_content')
    op.drop_column('orders', 'esp_device_id')


def downgrade():
    op.add_column('orders', sa.Column('board_id',      sa.Integer(), nullable=True))
    op.add_column('orders', sa.Column('svg_content',   sa.Text(),    nullable=True))
    op.add_column('orders', sa.Column('esp_device_id', sa.Integer(), nullable=True))

    # Restore single-item orders (one row per item, each gets its own cart_ref entry).
    # For simplicity, copy the first item's data back into the order row.
    op.execute("""
        UPDATE orders o
        SET board_id      = oi.board_id,
            svg_content   = oi.svg_content,
            amount_cents  = oi.amount_cents,
            esp_device_id = oi.esp_device_id
        FROM (
            SELECT DISTINCT ON (order_id) *
            FROM order_item
            ORDER BY order_id, id
        ) oi
        WHERE oi.order_id = o.id
    """)

    op.drop_table('order_item')
