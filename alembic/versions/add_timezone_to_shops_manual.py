"""add timezone to shops

Revision ID: add_timezone_to_shops_manual
Revises: b9e7400db9fa
Create Date: 2024-12-19 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_timezone_to_shops_manual'
down_revision = 'b9e7400db9fa'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add timezone column to shops table
    op.add_column('shops', sa.Column('timezone', sa.String(), nullable=False, server_default='America/Los_Angeles'))


def downgrade() -> None:
    # Remove timezone column from shops table
    op.drop_column('shops', 'timezone')