"""add_timezone_to_businesses

Revision ID: 34680070c523
Revises: add_timezone_to_shops_manual
Create Date: 2025-06-23 16:10:26.968825

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '34680070c523'
down_revision: Union[str, None] = 'add_timezone_to_shops_manual'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add timezone column to businesses table
    op.add_column('businesses', sa.Column('timezone', sa.String(), nullable=False, server_default='America/Los_Angeles'))


def downgrade() -> None:
    # Remove timezone column from businesses table
    op.drop_column('businesses', 'timezone')
