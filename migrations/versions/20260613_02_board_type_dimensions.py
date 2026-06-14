"""add physical dimension columns to board_type

Revision ID: 20260613_02
Revises: 20260613_01
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa

revision = '20260613_02'
down_revision = '20260613_01'
branch_labels = None
depends_on = None

_BIG = dict(
    max_width_mm=302.0, max_height_mm=212.0,
    delta_x_mm=16.0,    delta_y_mm=12.0,
    frame_inner_x_mm=287.0, frame_inner_y_mm=197.0,
    frame_outer_x_mm=317.0, frame_outer_y_mm=227.0,
    frame_overlap_x_mm=7.5, frame_overlap_y_mm=7.5,
)

_SMALL = dict(
    max_width_mm=182.0, max_height_mm=132.0,
    delta_x_mm=16.0,    delta_y_mm=12.0,
    frame_inner_x_mm=167.0, frame_inner_y_mm=117.0,
    frame_outer_x_mm=197.0, frame_outer_y_mm=147.0,
    frame_overlap_x_mm=7.5, frame_overlap_y_mm=7.5,
)


def upgrade():
    for col in (
        'max_width_mm', 'max_height_mm',
        'delta_x_mm', 'delta_y_mm',
        'frame_inner_x_mm', 'frame_inner_y_mm',
        'frame_outer_x_mm', 'frame_outer_y_mm',
        'frame_overlap_x_mm', 'frame_overlap_y_mm',
    ):
        op.add_column('board_type', sa.Column(col, sa.Float(), nullable=True))

    conn = op.get_bind()

    # Apply "small frame" values to any board_type whose name contains "small" (case-insensitive)
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
        WHERE LOWER(name) LIKE '%small%'
    """), _SMALL)

    # Apply "big frame" values to all other board types (name does not contain "small")
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
        WHERE LOWER(name) NOT LIKE '%small%'
    """), _BIG)


def downgrade():
    for col in (
        'max_width_mm', 'max_height_mm',
        'delta_x_mm', 'delta_y_mm',
        'frame_inner_x_mm', 'frame_inner_y_mm',
        'frame_outer_x_mm', 'frame_outer_y_mm',
        'frame_overlap_x_mm', 'frame_overlap_y_mm',
    ):
        op.drop_column('board_type', col)
