"""add quiet-hours schedule section to hardware settings schemas

Revision ID: 20260719_01
Revises: 20260703_02
Create Date: 2026-07-19
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260719_01"
down_revision: Union[str, tuple] = "20260703_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEDULE_SECTION = {
    "key": "schedule",
    "label": "Schedule",
    "settings": [
        {"key": "quiet_hours_enabled", "label": "Enable quiet hours", "type": "boolean", "default": False},
        {"key": "quiet_hours_start",   "label": "Quiet hours start",  "type": "time",    "default": "22:30"},
        {"key": "quiet_hours_end",     "label": "Quiet hours end",    "type": "time",    "default": "06:00"},
    ],
}


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, json_settings FROM hardware")).fetchall()
    for row_id, raw in rows:
        data = json.loads(raw) if raw else {}
        sections = data.get("sections", [])
        if any(s.get("key") == "schedule" for s in sections):
            continue
        sections.append(SCHEDULE_SECTION)
        data["sections"] = sections
        conn.execute(
            sa.text("UPDATE hardware SET json_settings = :js WHERE id = :id"),
            {"js": json.dumps(data), "id": row_id},
        )


def downgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, json_settings FROM hardware")).fetchall()
    for row_id, raw in rows:
        if not raw:
            continue
        data = json.loads(raw)
        sections = data.get("sections", [])
        new_sections = [s for s in sections if s.get("key") != "schedule"]
        if len(new_sections) == len(sections):
            continue
        data["sections"] = new_sections
        conn.execute(
            sa.text("UPDATE hardware SET json_settings = :js WHERE id = :id"),
            {"js": json.dumps(data), "id": row_id},
        )
