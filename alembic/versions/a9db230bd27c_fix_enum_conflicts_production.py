"""fix_enum_conflicts_production

Revision ID: a9db230bd27c
Revises: 6cbf0a1b20f6
Create Date: 2025-06-09 23:08:28.041329

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a9db230bd27c'
down_revision: Union[str, None] = '6cbf0a1b20f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def enum_exists(conn, enum_name: str) -> bool:
    """Check if a PostgreSQL ENUM type exists."""
    result = conn.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = :enum_name"),
        {"enum_name": enum_name}
    ).fetchone()
    return result is not None


def create_enum_if_not_exists(conn, enum_name: str, enum_values: list):
    """Create ENUM type only if it doesn't already exist."""
    if not enum_exists(conn, enum_name):
        enum_type = postgresql.ENUM(*enum_values, name=enum_name)
        enum_type.create(conn)
        print(f"Created ENUM type: {enum_name}")
    else:
        print(f"ENUM type already exists: {enum_name}")


def upgrade() -> None:
    """Safely create all required ENUM types, checking for existence first."""
    conn = op.get_bind()
    
    # Create all required ENUM types safely
    create_enum_if_not_exists(conn, 'userrole', ['USER', 'SHOP_OWNER', 'BARBER', 'ADMIN'])
    create_enum_if_not_exists(conn, 'barberstatus', ['AVAILABLE', 'IN_SERVICE', 'ON_BREAK', 'OFF'])
    create_enum_if_not_exists(conn, 'appointmentstatus', ['SCHEDULED', 'COMPLETED', 'CANCELLED'])
    create_enum_if_not_exists(conn, 'scheduletype', ['WORKING', 'BREAK', 'OFF'])
    create_enum_if_not_exists(conn, 'queuestatus', ['ARRIVED', 'CHECKED_IN', 'IN_SERVICE', 'COMPLETED', 'CANCELLED'])
    create_enum_if_not_exists(conn, 'schedulerepeatfrequency', ['NONE', 'DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY'])
    
    # Ensure users table has is_first_login column
    # Check if column exists before adding
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('users')]
    
    if 'is_first_login' not in columns:
        op.add_column('users', sa.Column('is_first_login', sa.Boolean(), nullable=False, server_default='true'))
        print("Added is_first_login column to users table")
    else:
        print("is_first_login column already exists in users table")
    
    # Check and add reset token fields if they don't exist
    if 'reset_token' not in columns:
        op.add_column('users', sa.Column('reset_token', sa.String(), nullable=True))
        op.create_index('ix_users_reset_token', 'users', ['reset_token'], unique=False)
        print("Added reset_token column to users table")
    else:
        print("reset_token column already exists in users table")
        
    if 'reset_token_expires' not in columns:
        op.add_column('users', sa.Column('reset_token_expires', sa.DateTime(timezone=True), nullable=True))
        print("Added reset_token_expires column to users table")
    else:
        print("reset_token_expires column already exists in users table")


def downgrade() -> None:
    """This migration is designed to be safe and non-destructive, no downgrade needed."""
    pass
