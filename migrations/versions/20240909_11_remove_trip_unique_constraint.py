"""Remove unique constraint on trip start/terminus

Revision ID: 20240909_11
Revises: 20240909_10
Create Date: 2024-09-09 00:00:11.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20240909_11"
down_revision = "20240909_10"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("uq_terminus_start_line", "trip", type_="unique")


def downgrade():
    op.create_unique_constraint(
        "uq_terminus_start_line",
        "trip",
        [
            "terminus_stop_id",
            "terminus_agency_name",
            "start_stop_id",
            "start_agency_name",
            "line_id",
            "line_agency_name",
            "direction",
        ],
    )
