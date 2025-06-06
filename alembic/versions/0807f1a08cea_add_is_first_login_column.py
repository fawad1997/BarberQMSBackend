"""add_is_first_login_column

Revision ID: 0807f1a08cea
Revises: 8f2ca4d6d0f4
Create Date: 2025-06-06 18:56:29.943820

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0807f1a08cea'
down_revision: Union[str, None] = '8f2ca4d6d0f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_first_login column to users table
    op.add_column('users', sa.Column('is_first_login', sa.Boolean(), nullable=False, server_default='true'))


def downgrade() -> None:
    # Remove is_first_login column from users table
    op.drop_column('users', 'is_first_login')
