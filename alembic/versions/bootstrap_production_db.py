"""bootstrap_production_db

Revision ID: bootstrap_production_db
Revises: a9db230bd27c
Create Date: 2025-06-09 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'bootstrap_production_db'
down_revision: Union[str, None] = 'a9db230bd27c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def table_exists(conn, table_name: str) -> bool:
    """Check if a table exists in the database."""
    result = conn.execute(
        sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = :table_name
        )
        """),
        {"table_name": table_name}
    ).fetchone()
    return result[0] if result else False


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


def create_table_if_not_exists(conn, table_name: str, create_func):
    """Create table only if it doesn't exist."""
    if not table_exists(conn, table_name):
        create_func()
        print(f"Created table: {table_name}")
    else:
        print(f"Table already exists: {table_name}")


def upgrade() -> None:
    """Bootstrap the production database with all required schema."""
    conn = op.get_bind()
    
    print("=== STARTING PRODUCTION DATABASE BOOTSTRAP ===")
    
    # Step 1: Create all ENUM types safely
    print("Creating ENUM types...")
    create_enum_if_not_exists(conn, 'userrole', ['USER', 'SHOP_OWNER', 'BARBER', 'ADMIN'])
    create_enum_if_not_exists(conn, 'barberstatus', ['AVAILABLE', 'IN_SERVICE', 'ON_BREAK', 'OFF'])
    create_enum_if_not_exists(conn, 'appointmentstatus', ['SCHEDULED', 'COMPLETED', 'CANCELLED'])
    create_enum_if_not_exists(conn, 'scheduletype', ['WORKING', 'BREAK', 'OFF'])
    create_enum_if_not_exists(conn, 'queuestatus', ['ARRIVED', 'CHECKED_IN', 'IN_SERVICE', 'COMPLETED', 'CANCELLED'])
    create_enum_if_not_exists(conn, 'schedulerepeatfrequency', ['NONE', 'DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY'])
    
    # Step 2: Create core tables if they don't exist
    print("Creating tables...")
    
    # Users table
    def create_users_table():
        op.create_table('users',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('full_name', sa.String(), nullable=False),
            sa.Column('phone_number', sa.String(), nullable=True),
            sa.Column('email', sa.String(), nullable=True),
            sa.Column('hashed_password', sa.String(), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
            sa.Column('role', sa.Enum('USER', 'SHOP_OWNER', 'BARBER', 'ADMIN', name='userrole'), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.Column('is_first_login', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('reset_token', sa.String(), nullable=True),
            sa.Column('reset_token_expires', sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_users_email', 'users', ['email'], unique=True)
        op.create_index('ix_users_id', 'users', ['id'], unique=False)
        op.create_index('ix_users_phone_number', 'users', ['phone_number'], unique=True)
        op.create_index('ix_users_reset_token', 'users', ['reset_token'], unique=False)
    
    create_table_if_not_exists(conn, 'users', create_users_table)
    
    # If users table exists, ensure it has all required columns
    if table_exists(conn, 'users'):
        print("Checking users table columns...")
        inspector = sa.inspect(conn)
        columns = [col['name'] for col in inspector.get_columns('users')]
        
        if 'is_first_login' not in columns:
            op.add_column('users', sa.Column('is_first_login', sa.Boolean(), nullable=False, server_default='true'))
            print("Added is_first_login column to users table")
            
        if 'reset_token' not in columns:
            op.add_column('users', sa.Column('reset_token', sa.String(), nullable=True))
            op.create_index('ix_users_reset_token', 'users', ['reset_token'], unique=False)
            print("Added reset_token column to users table")
            
        if 'reset_token_expires' not in columns:
            op.add_column('users', sa.Column('reset_token_expires', sa.DateTime(timezone=True), nullable=True))
            print("Added reset_token_expires column to users table")
    
    # Shops table
    def create_shops_table():
        op.create_table('shops',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('slug', sa.String(), nullable=False),
            sa.Column('username', sa.String(), nullable=True),
            sa.Column('address', sa.String(), nullable=False),
            sa.Column('city', sa.String(), nullable=False),
            sa.Column('state', sa.String(), nullable=False),
            sa.Column('zip_code', sa.String(), nullable=False),
            sa.Column('phone_number', sa.String(), nullable=True),
            sa.Column('email', sa.String(), nullable=True),
            sa.Column('owner_id', sa.Integer(), nullable=False),
            sa.Column('opening_time', sa.Time(), nullable=False),
            sa.Column('closing_time', sa.Time(), nullable=False),
            sa.Column('average_wait_time', sa.Float(), nullable=True),
            sa.Column('has_advertisement', sa.Boolean(), nullable=True),
            sa.Column('advertisement_image_url', sa.String(), nullable=True),
            sa.Column('advertisement_start_date', sa.DateTime(), nullable=True),
            sa.Column('advertisement_end_date', sa.DateTime(), nullable=True),
            sa.Column('is_advertisement_active', sa.Boolean(), nullable=True),
            sa.Column('is_open_24_hours', sa.Boolean(), default=False),
            sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('slug'),
            sa.UniqueConstraint('username')
        )
        op.create_index('ix_shops_id', 'shops', ['id'], unique=False)
        op.create_index('ix_shops_slug', 'shops', ['slug'], unique=True)
        op.create_index('ix_shops_username', 'shops', ['username'], unique=True)
    
    create_table_if_not_exists(conn, 'shops', create_shops_table)
    
    print("=== PRODUCTION DATABASE BOOTSTRAP COMPLETE ===")


def downgrade() -> None:
    """This is a bootstrap migration - no downgrade."""
    pass
