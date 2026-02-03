"""Add direction column to trip

Revision ID: 20240909_04_add_direction_to_trip
Revises: 20240909_03_create_order_table
Create Date: 2024-09-09 00:00:04.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20240909_04'
down_revision = '20240909_03'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    has_direction = any(col["name"] == "direction" for col in insp.get_columns("trip"))
    if not has_direction:
        # add column with temporary default to backfill existing rows
        op.add_column('trip', sa.Column('direction', sa.Integer(), server_default='0', nullable=False))
        # drop default for future inserts
        op.alter_column('trip', 'direction', server_default=None)

    # refresh unique constraint to include direction
    existing_uk = [uc["name"] for uc in insp.get_unique_constraints("trip")]
    if "uq_terminus_start_line" in existing_uk:
        op.drop_constraint('uq_terminus_start_line', 'trip', type_='unique')

    op.create_unique_constraint(
        'uq_terminus_start_line',
        'trip',
        [
            'terminus_stop_id', 'terminus_agency_name',
            'start_stop_id', 'start_agency_name',
            'line_id', 'line_agency_name',
            'direction'
        ]
    )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    existing_uk = [uc["name"] for uc in insp.get_unique_constraints("trip")]
    if "uq_terminus_start_line" in existing_uk:
        op.drop_constraint('uq_terminus_start_line', 'trip', type_='unique')

    op.create_unique_constraint(
        'uq_terminus_start_line',
        'trip',
        [
            'terminus_stop_id', 'terminus_agency_name',
            'start_stop_id', 'start_agency_name',
            'line_id', 'line_agency_name'
        ]
    )

    has_direction = any(col["name"] == "direction" for col in insp.get_columns("trip"))
    if has_direction:
        op.drop_column('trip', 'direction')
