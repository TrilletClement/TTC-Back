"""Add line disruption alerts tables (GTFS-RT alert feeds).

Revision ID: 20260803_01
Revises: 20260724_01
Create Date: 2026-08-03
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260803_01"
down_revision: Union[str, None] = "20260724_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "line_alert",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("agency_name", sa.String(100), sa.ForeignKey("agency.name"), nullable=False),
        sa.Column("gtfs_alert_id", sa.String(100), nullable=False),
        sa.Column("effect", sa.String(50), nullable=True),
        sa.Column("header_text", sa.Text, nullable=False),
        sa.Column("description_text", sa.Text, nullable=True),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("fetched_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "line_alert_line",
        sa.Column("line_id", sa.Integer, sa.ForeignKey("line.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("alert_id", sa.Integer, sa.ForeignKey("line_alert.id", ondelete="CASCADE"), primary_key=True),
    )

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


def downgrade() -> None:
    op.drop_table("alert_global_setting")
    op.drop_table("alert_agency_setting")
    op.drop_table("line_alert_line")
    op.drop_table("line_alert")
