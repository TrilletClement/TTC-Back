"""Reverse led_strip.order_index per board to match real hardware numbering.

order_index used to mean "1 = topmost strip, ascending downward" everywhere
(admin board editor, SVG label export, and the value sent to the ESP32 as
`h`). Real hardware numbers its physical strips the other way — "1 = bottom
strip, ascending upward" — so every board's numbering was inverted relative
to the ESP32's own indexing. Application code (board_svg_service.py,
led-visualization.ts) was updated to render order_index the new way, so this
migration only swaps the stored values — it does not move any strip
visually on the website, it just relabels them (see those files' history
for the rendering-side half of this fix).

For each strip: new_order_index = board_type.max_ledstrip + 1 - order_index.
This is its own inverse, so upgrade() and downgrade() run the identical swap.

Revision ID: 20260722_01
Revises: 20260720_04
Create Date: 2026-07-22
"""
from typing import Sequence, Union
from alembic import op

revision: str = "20260722_01"
down_revision: Union[str, None] = "20260720_04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SWAP_SQL = """
    UPDATE led_strip
    SET order_index = bt.max_ledstrip + 1 - led_strip.order_index
    FROM board b
    JOIN board_type bt ON bt.id = b.board_type_id
    WHERE b.id = led_strip.board_id
"""


def upgrade() -> None:
    op.execute(_SWAP_SQL)


def downgrade() -> None:
    op.execute(_SWAP_SQL)
