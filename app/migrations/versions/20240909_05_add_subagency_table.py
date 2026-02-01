"""Create subagency table

Revision ID: 20240909_05
Revises: 20240909_04
Create Date: 2024-09-09 00:00:05.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20240909_05'
down_revision = '20240909_04'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'subagency',
        sa.Column('id', sa.String(length=10), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('agency_name', sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint('id', 'agency_name', name='pk_subagency_id_agency'),
        sa.ForeignKeyConstraint(['agency_name'], ['agency.name'], ondelete='CASCADE'),
        sa.UniqueConstraint('name', name='uq_subagency_name')
    )


def downgrade():
    op.drop_table('subagency')
