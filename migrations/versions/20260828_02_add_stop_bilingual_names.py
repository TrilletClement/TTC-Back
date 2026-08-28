"""add stop.name_fr/name_nl and led_strip.stop_name_language

Revision ID: 20260828_02
Revises: 20260828_01
Create Date: 2026-08-28

STIB and SNCB feeds bake both languages into stop_name as a single string
("GARE DU MIDI/ZUIDSTATION") with no per-language columns; TEC and De Lijn
are monolingual (French and Dutch respectively). name_fr/name_nl split that
out so a board's LED labels can show just the language the user picked at
creation time (led_strip.stop_name_language) instead of the raw combined
string. Backfilled here from existing data with the same split rule
_import_stops (gtfs_import.py) now applies going forward, so the feature
works immediately rather than waiting for the next GTFS reimport.
"""
from alembic import op
import sqlalchemy as sa

revision = '20260828_02'
down_revision = '20260828_01'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('stop', sa.Column('name_fr', sa.String(100), nullable=True))
    op.add_column('stop', sa.Column('name_nl', sa.String(100), nullable=True))
    op.add_column('led_strip', sa.Column('stop_name_language', sa.String(2), nullable=True))

    conn = op.get_bind()
    # STIB / SNCB: split "FR/NL" combined names on the separator where
    # present. A handful of stops (depots, etc.) have no slash — those stay
    # French-only (name_nl left NULL, there's no Dutch text to extract).
    conn.execute(sa.text("""
        UPDATE stop SET
            name_fr = TRIM(split_part(name, '/', 1)),
            name_nl = CASE WHEN name LIKE '%/%' THEN TRIM(split_part(name, '/', 2)) END
        WHERE agency_name IN ('STIB', 'SNCB')
    """))
    conn.execute(sa.text("UPDATE stop SET name_fr = name WHERE agency_name = 'TEC'"))
    conn.execute(sa.text("UPDATE stop SET name_nl = name WHERE agency_name = 'DE_LIJN'"))


def downgrade():
    op.drop_column('led_strip', 'stop_name_language')
    op.drop_column('stop', 'name_nl')
    op.drop_column('stop', 'name_fr')
