"""Add signature to trip and ensure gtfs_trip table

Revision ID: 20240909_10
Revises: 20240909_09
Create Date: 2024-09-09 00:00:10.000000
"""

from alembic import op
import sqlalchemy as sa
import hashlib


# revision identifiers, used by Alembic.
revision = "20240909_10"
down_revision = "20240909_09"
branch_labels = None
depends_on = None


def _build_signature(line_id, direction, stop_ids):
    payload = f"{line_id}:{direction}|" + "|".join(stop_ids)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def upgrade():
    bind = op.get_bind()
    if not bind.dialect.has_table(bind, "gtfs_trip"):
        op.create_table(
            "gtfs_trip",
            sa.Column("id", sa.String(length=100), nullable=False),
            sa.Column("trip_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["trip_id"], ["trip.id"]),
            sa.PrimaryKeyConstraint("id", "trip_id", name="pk_gtfs_trip_composite"),
        )

    op.add_column("trip", sa.Column("signature", sa.String(length=64), nullable=True))

    conn = op.get_bind()
    trip_meta = {
        row.id: (row.line_id, row.direction)
        for row in conn.execute(sa.text("SELECT id, line_id, direction FROM trip"))
    }

    stop_map = {}
    for row in conn.execute(
        sa.text("SELECT trip_id, stop_stop_id FROM trip_stop ORDER BY trip_id, sequence")
    ):
        stop_map.setdefault(row.trip_id, []).append(row.stop_stop_id)

    updates = []
    for trip_id, meta in trip_meta.items():
        stops = stop_map.get(trip_id)
        if not stops:
            continue
        line_id, direction = meta
        signature = _build_signature(line_id, direction, stops)
        updates.append({"id": trip_id, "signature": signature})

    if updates:
        conn.execute(
            sa.text("UPDATE trip SET signature = :signature WHERE id = :id"),
            updates,
        )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.has_table(bind, "gtfs_trip"):
        op.drop_table("gtfs_trip")
    op.drop_column("trip", "signature")
