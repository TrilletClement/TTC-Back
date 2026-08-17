"""Backfill real per-line colors for TEC lines.

TEC's static GTFS feed reports the placeholder route_color #FFCD00 for
every line (confirmed: all TEC rows in `line` currently hold exactly that
value), so real colors come from TEC_LINE_COLORS
(app/core/tec_line_colors.py), keyed by the Hastus line ID embedded in
route_id ("gr:tec:B0210-24013" -> "B0210"). `_import_lines`
(app/routines/gtfs_import.py) was updated to apply this same mapping on
every future TEC import, so the nightly re-import doesn't clobber this
backfill back to #FFCD00.

Revision ID: 20260817_03
Revises: 20260817_02
Create Date: 2026-08-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.tec_line_colors import TEC_LINE_COLORS

revision: str = "20260817_03"
down_revision: Union[str, None] = "20260817_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PLACEHOLDER_COLOR = "#FFCD00"

# route_id looks like "gr:tec:{hastus_id}-{release}" — split_part gets the
# hastus_id back out without needing a regex.
_HASTUS_ID_EXPR = "split_part(split_part(route_id, ':', 3), '-', 1)"


def upgrade() -> None:
    bind = op.get_bind()
    stmt = sa.text(
        f"UPDATE line SET color = :color "
        f"WHERE agency_name = 'TEC' AND {_HASTUS_ID_EXPR} = :hastus_id"
    )
    for hastus_id, color in TEC_LINE_COLORS.items():
        bind.execute(stmt, {"hastus_id": hastus_id, "color": color})


def downgrade() -> None:
    bind = op.get_bind()
    stmt = sa.text(
        f"UPDATE line SET color = :placeholder "
        f"WHERE agency_name = 'TEC' AND {_HASTUS_ID_EXPR} = :hastus_id"
    )
    for hastus_id in TEC_LINE_COLORS:
        bind.execute(stmt, {"hastus_id": hastus_id, "placeholder": PLACEHOLDER_COLOR})
