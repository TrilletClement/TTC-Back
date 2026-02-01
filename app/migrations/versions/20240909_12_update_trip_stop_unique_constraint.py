"""Update trip_stop unique constraint to use sequence

Revision ID: 20240909_12
Revises: 20240909_11
Create Date: 2024-09-09 00:00:12.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20240909_12"
down_revision = "20240909_11"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("uq_trip_stop", "trip_stop", type_="unique")
    op.create_unique_constraint("uq_trip_stop_sequence", "trip_stop", ["trip_id", "sequence"])


def downgrade():
    op.drop_constraint("uq_trip_stop_sequence", "trip_stop", type_="unique")
    op.create_unique_constraint(
        "uq_trip_stop",
        "trip_stop",
        ["trip_id", "stop_stop_id", "stop_agency_name"],
    )
