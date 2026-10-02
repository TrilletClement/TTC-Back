"""Add push_device, departure_alert and departure_alert_sent tables.

"Time to leave" notifications of the Android app: phones (FCM tokens), the
alerts users configure on their strips, and the per-vehicle dedup log.

Revision ID: 20261002_01
Revises: 20260917_01
Create Date: 2026-10-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20261002_01"
down_revision: Union[str, None] = "20260917_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "push_device",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(length=512), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False, server_default="android"),
        sa.Column("lang", sa.String(length=5), nullable=False, server_default="fr"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_push_device_user_id", "push_device", ["user_id"])
    op.create_unique_constraint("uq_push_device_token", "push_device", ["token"])

    op.create_table(
        "departure_alert",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("led_strip_id", sa.Integer(), sa.ForeignKey("led_strip.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stop_keys", sa.JSON(), nullable=False),
        sa.Column("stop_name", sa.String(length=100), nullable=False),
        sa.Column("direction", sa.Integer(), nullable=True),
        sa.Column("trigger", sa.String(length=10), nullable=False, server_default="minutes"),
        sa.Column("minutes_before", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("windows", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_departure_alert_user_id", "departure_alert", ["user_id"])
    op.create_index("ix_departure_alert_led_strip_id", "departure_alert", ["led_strip_id"])

    op.create_table(
        "departure_alert_sent",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alert_id", sa.Integer(), sa.ForeignKey("departure_alert.id", ondelete="CASCADE"), nullable=False),
        sa.Column("raw_trip_id", sa.Integer(), nullable=False),
        sa.Column("service_date", sa.String(length=8), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("alert_id", "raw_trip_id", "service_date", name="uq_departure_alert_sent_trip"),
    )
    op.create_index("ix_departure_alert_sent_sent_at", "departure_alert_sent", ["sent_at"])


def downgrade() -> None:
    op.drop_index("ix_departure_alert_sent_sent_at", table_name="departure_alert_sent")
    op.drop_table("departure_alert_sent")
    op.drop_index("ix_departure_alert_led_strip_id", table_name="departure_alert")
    op.drop_index("ix_departure_alert_user_id", table_name="departure_alert")
    op.drop_table("departure_alert")
    op.drop_index("ix_push_device_user_id", table_name="push_device")
    op.drop_table("push_device")
