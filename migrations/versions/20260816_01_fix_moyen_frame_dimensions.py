"""fix board_type physical dimensions for the 3-strip "Moyen Frame" type

Revision ID: 20260816_01
Revises: 20260806_02
Create Date: 2026-08-16

20260613_02_board_type_dimensions.py seeded physical dimensions with a
two-bucket `WHERE name LIKE '%small%'` / `NOT LIKE '%small%'` split, so
"Moyen Frame" (max_ledstrip=3) silently fell into the "big" bucket and got
an exact copy of Big Frame's (max_ledstrip=4) dimensions. That mismatch
between the SVG canvas size (sized for Big Frame) and the actually-drawn
3-strip content (sized correctly for Moyen) is what produced the tiny,
off-center "Aperçu du board (avec cadre)" preview reported for 3-strip
boards.

The values below are a **linear interpolation** between Small Frame
(max_led=10, max_ledstrip=2) and Big Frame (max_led=16, max_ledstrip=4) —
width-related columns interpolated on max_led, height-related columns on
max_ledstrip. They reproduce the exact same width/frame-inner and
frame-inner/frame-outer margins (15mm, 30mm) found on both known rows, so
they're structurally consistent, but are NOT verified physical
measurements — replace with the real Moyen Frame spec if/when available.
"""
from alembic import op
import sqlalchemy as sa

revision = '20260816_01'
down_revision = '20260806_02'
branch_labels = None
depends_on = None

_MOYEN = dict(
    max_width_mm=222.0, max_height_mm=172.0,
    delta_x_mm=16.0,    delta_y_mm=12.0,
    frame_inner_x_mm=207.0, frame_inner_y_mm=157.0,
    frame_outer_x_mm=237.0, frame_outer_y_mm=187.0,
    frame_overlap_x_mm=7.5, frame_overlap_y_mm=7.5,
)

_BIG = dict(
    max_width_mm=302.0, max_height_mm=212.0,
    delta_x_mm=16.0,    delta_y_mm=12.0,
    frame_inner_x_mm=287.0, frame_inner_y_mm=197.0,
    frame_outer_x_mm=317.0, frame_outer_y_mm=227.0,
    frame_overlap_x_mm=7.5, frame_overlap_y_mm=7.5,
)


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE board_type SET
            max_width_mm       = :max_width_mm,
            max_height_mm      = :max_height_mm,
            delta_x_mm         = :delta_x_mm,
            delta_y_mm         = :delta_y_mm,
            frame_inner_x_mm   = :frame_inner_x_mm,
            frame_inner_y_mm   = :frame_inner_y_mm,
            frame_outer_x_mm   = :frame_outer_x_mm,
            frame_outer_y_mm   = :frame_outer_y_mm,
            frame_overlap_x_mm = :frame_overlap_x_mm,
            frame_overlap_y_mm = :frame_overlap_y_mm
        WHERE max_ledstrip = 3
    """), _MOYEN)


def downgrade():
    # Restores the pre-fix (buggy, Big-Frame-duplicate) state so this
    # migration is a clean no-op round trip.
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE board_type SET
            max_width_mm       = :max_width_mm,
            max_height_mm      = :max_height_mm,
            delta_x_mm         = :delta_x_mm,
            delta_y_mm         = :delta_y_mm,
            frame_inner_x_mm   = :frame_inner_x_mm,
            frame_inner_y_mm   = :frame_inner_y_mm,
            frame_outer_x_mm   = :frame_outer_x_mm,
            frame_outer_y_mm   = :frame_outer_y_mm,
            frame_overlap_x_mm = :frame_overlap_x_mm,
            frame_overlap_y_mm = :frame_overlap_y_mm
        WHERE max_ledstrip = 3
    """), _BIG)
