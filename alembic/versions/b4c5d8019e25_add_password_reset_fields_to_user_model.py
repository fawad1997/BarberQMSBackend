"""Add password reset fields to user model

Revision ID: b4c5d8019e25
Revises: 3b8afedc0e3d
Create Date: 2025-05-30 11:21:05.154824

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4c5d8019e25'
down_revision: Union[str, None] = '3b8afedc0e3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add password reset fields to users table
    op.add_column('users', sa.Column('reset_token', sa.String(), nullable=True))
    op.add_column('users', sa.Column('reset_token_expires', sa.DateTime(timezone=True), nullable=True))
    
    # Create index on reset_token for faster lookups
    op.create_index('ix_users_reset_token', 'users', ['reset_token'])


def downgrade() -> None:
    # Remove index and columns
    op.drop_index('ix_users_reset_token', table_name='users')
    op.drop_column('users', 'reset_token_expires')
    op.drop_column('users', 'reset_token')
