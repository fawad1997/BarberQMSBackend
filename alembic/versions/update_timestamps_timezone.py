"""update_timestamps_timezone

Revision ID: update_timestamps_timezone
Revises: 6a092695a76d
Create Date: 2024-04-30 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'update_timestamps_timezone'
down_revision: Union[str, None] = '6a092695a76d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table, column):
    # Check if column exists in table
    connection = op.get_bind()
    result = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :column)"
        ),
        {"table": table, "column": column}
    ).scalar()
    return result


def upgrade() -> None:
    # Convert timestamp columns to timezone-aware
    if column_exists('barber_schedules', 'start_date'):
        op.alter_column('barber_schedules', 'start_date',
                        type_=sa.DateTime(timezone=True),
                        postgresql_using='start_date AT TIME ZONE \'UTC\'')
    
    if column_exists('barber_schedules', 'end_date'):
        op.alter_column('barber_schedules', 'end_date',
                        type_=sa.DateTime(timezone=True),
                        postgresql_using='end_date AT TIME ZONE \'UTC\'')
    
    if column_exists('barber_schedules', 'created_at'):
        op.alter_column('barber_schedules', 'created_at',
                        type_=sa.DateTime(timezone=True),
                        postgresql_using='created_at AT TIME ZONE \'UTC\'',
                        server_default=sa.text('now()'))
    
    if column_exists('barber_schedules', 'updated_at'):
        op.alter_column('barber_schedules', 'updated_at',
                        type_=sa.DateTime(timezone=True),
                        postgresql_using='updated_at AT TIME ZONE \'UTC\'',
                        server_default=sa.text('now()'))


def downgrade() -> None:
    # Convert timestamp columns back to timezone-naive
    if column_exists('barber_schedules', 'start_date'):
        op.alter_column('barber_schedules', 'start_date',
                        type_=sa.DateTime(),
                        postgresql_using='start_date AT TIME ZONE \'UTC\'')
    
    if column_exists('barber_schedules', 'end_date'):
        op.alter_column('barber_schedules', 'end_date',
                        type_=sa.DateTime(),
                        postgresql_using='end_date AT TIME ZONE \'UTC\'')
    
    if column_exists('barber_schedules', 'created_at'):
        op.alter_column('barber_schedules', 'created_at',
                        type_=sa.DateTime(),
                        postgresql_using='created_at AT TIME ZONE \'UTC\'',
                        server_default=sa.text('now()'))
    
    if column_exists('barber_schedules', 'updated_at'):
        op.alter_column('barber_schedules', 'updated_at',
                        type_=sa.DateTime(),
                        postgresql_using='updated_at AT TIME ZONE \'UTC\'',
                        server_default=sa.text('now()')) 