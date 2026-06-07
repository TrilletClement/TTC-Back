"""board_type_not_null — prune boards without a board type, then make board_type_id NOT NULL.

Delete cascade order for orphaned boards (board_type_id IS NULL):
  1. trip_stop_led_link rows whose led_id belongs to a strip on those boards
  2. led rows in those strips
  3. led_strip rows for those boards
  4. NULL out esp32_device.board_id for devices linked to those boards
  5. DELETE the board rows

Revision ID: 20260607_01_board_type_not_null
Revises: 20260605_01_cert_serial_bigint_to_numeric, bb1f31bb2aa6
Create Date: 2026-06-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260607_01_board_type_not_null"
down_revision: Union[str, tuple] = (
    "20260605_01_cert_serial_bigint_to_numeric",
    "bb1f31bb2aa6",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. trip_stop_led_link rows linked to LEDs on orphaned boards
    conn.execute(sa.text("""
        DELETE FROM trip_stop_led_link
        WHERE led_id IN (
            SELECT l.id FROM led l
            JOIN led_strip ls ON l.ledstrip_id = ls.id
            JOIN board b      ON ls.board_id   = b.id
            WHERE b.board_type_id IS NULL
        )
    """))

    # 2. led rows for those strips
    conn.execute(sa.text("""
        DELETE FROM led
        WHERE ledstrip_id IN (
            SELECT ls.id FROM led_strip ls
            JOIN board b ON ls.board_id = b.id
            WHERE b.board_type_id IS NULL
        )
    """))

    # 3. led_strip rows for those boards
    conn.execute(sa.text("""
        DELETE FROM led_strip
        WHERE board_id IN (
            SELECT id FROM board WHERE board_type_id IS NULL
        )
    """))

    # 4. NULL out esp32_device.board_id for devices linked to those boards
    conn.execute(sa.text("""
        UPDATE esp32_device
        SET board_id = NULL
        WHERE board_id IN (
            SELECT id FROM board WHERE board_type_id IS NULL
        )
    """))

    # 5. Delete the boards themselves
    conn.execute(sa.text("""
        DELETE FROM board WHERE board_type_id IS NULL
    """))

    # 6. Now safe to make the column NOT NULL
    op.alter_column("board", "board_type_id", nullable=False)


def downgrade() -> None:
    op.alter_column("board", "board_type_id", nullable=True)
