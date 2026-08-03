"""Drop admin-controlled alert settings — display is now purely per-user.

Revision ID: 20260803_03
Revises: 20260803_02
Create Date: 2026-08-03
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260803_03"
down_revision: Union[str, None] = "20260803_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("alert_agency_setting")
    op.drop_table("alert_global_setting")


def downgrade() -> None:
    op.create_table(
        "alert_agency_setting",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("agency_name", sa.String(100), sa.ForeignKey("agency.name"), unique=True, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
    )
    op.execute(
        "INSERT INTO alert_agency_setting (agency_name, enabled) "
        "SELECT name, true FROM agency WHERE name IN ('TEC', 'DE_LIJN', 'SNCB') "
        "ON CONFLICT DO NOTHING"
    )
    op.create_table(
        "alert_global_setting",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("display_mode", sa.String(10), nullable=False, server_default="banner"),
    )
    op.execute("INSERT INTO alert_global_setting (id, display_mode) VALUES (1, 'banner')")
