"""add timezone to shops

Revision ID: add_timezone_to_shops_manual
Revises: 255fc4fcffdc
Create Date: 2024-12-19 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_timezone_to_shops_manual'
down_revision = '255fc4fcffdc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add timezone column to shops table if it doesn't exist
    from sqlalchemy import inspect
    from sqlalchemy.engine import reflection
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [c['name'] for c in inspector.get_columns('shops')]
    
    if 'timezone' not in columns:
        op.add_column('shops', sa.Column('timezone', sa.String(), nullable=False, server_default='America/Los_Angeles'))


def downgrade() -> None:
    # Remove timezone column from shops table
    op.drop_column('shops', 'timezone')