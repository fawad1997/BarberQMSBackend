"""update_barber_schedule_schema

Revision ID: fff50fee97e4
Revises: 0920b2ad538d
Create Date: 2025-04-30 03:10:05.535626

"""
from typing import Sequence, Union
from datetime import datetime, time

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'fff50fee97e4'
down_revision: Union[str, None] = '0920b2ad538d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the enum type if it doesn't exist
    connection = op.get_bind()
    result = connection.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'schedulerepeatfrequency')")
    ).scalar()
    
    if not result:
        op.execute("CREATE TYPE schedulerepeatfrequency AS ENUM ('NONE', 'DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY')")
    
    # Add new columns as nullable
    op.add_column('barber_schedules', sa.Column('start_date', sa.DateTime(), nullable=True))
    op.add_column('barber_schedules', sa.Column('end_date', sa.DateTime(), nullable=True))
    op.add_column('barber_schedules', sa.Column('repeat_frequency', sa.Enum('NONE', 'DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY', name='schedulerepeatfrequency'), nullable=True))
    op.add_column('barber_schedules', sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True))
    op.add_column('barber_schedules', sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True))
    
    # Migrate existing data
    schedules = connection.execute(
        sa.text("SELECT id, day_of_week, start_time, end_time FROM barber_schedules")
    ).fetchall()
    
    for schedule in schedules:
        # Convert day_of_week to a date (using Monday as day 0)
        base_date = datetime(2024, 1, 1)  # Using 2024 as a base year
        schedule_date = base_date.replace(day=base_date.day + schedule.day_of_week)
        
        # Combine date with time
        start_datetime = datetime.combine(schedule_date.date(), schedule.start_time)
        end_datetime = datetime.combine(schedule_date.date(), schedule.end_time)
        
        # Update the record
        connection.execute(
            sa.text("""
                UPDATE barber_schedules 
                SET start_date = :start_date,
                    end_date = :end_date,
                    repeat_frequency = 'WEEKLY'
                WHERE id = :id
            """),
            {
                'start_date': start_datetime,
                'end_date': end_datetime,
                'id': schedule.id
            }
        )
    
    # Make columns non-nullable
    op.alter_column('barber_schedules', 'start_date', nullable=False)
    op.alter_column('barber_schedules', 'end_date', nullable=False)
    op.alter_column('barber_schedules', 'repeat_frequency', nullable=False)
    
    # Drop old columns and constraints
    op.drop_constraint('uix_barber_day', 'barber_schedules', type_='unique')
    op.drop_column('barber_schedules', 'day_of_week')
    op.drop_column('barber_schedules', 'end_time')
    op.drop_column('barber_schedules', 'start_time')


def downgrade() -> None:
    # Add back old columns
    op.add_column('barber_schedules', sa.Column('start_time', postgresql.TIME(), autoincrement=False, nullable=True))
    op.add_column('barber_schedules', sa.Column('end_time', postgresql.TIME(), autoincrement=False, nullable=True))
    op.add_column('barber_schedules', sa.Column('day_of_week', sa.INTEGER(), autoincrement=False, nullable=True))
    
    # Migrate data back
    connection = op.get_bind()
    schedules = connection.execute(
        sa.text("SELECT id, start_date, end_date FROM barber_schedules")
    ).fetchall()
    
    for schedule in schedules:
        connection.execute(
            sa.text("""
                UPDATE barber_schedules 
                SET start_time = :start_time,
                    end_time = :end_time,
                    day_of_week = :day_of_week
                WHERE id = :id
            """),
            {
                'start_time': schedule.start_date.time(),
                'end_time': schedule.end_date.time(),
                'day_of_week': schedule.start_date.weekday(),
                'id': schedule.id
            }
        )
    
    # Make old columns non-nullable
    op.alter_column('barber_schedules', 'start_time', nullable=False)
    op.alter_column('barber_schedules', 'end_time', nullable=False)
    op.alter_column('barber_schedules', 'day_of_week', nullable=False)
    
    # Add back constraints
    op.create_unique_constraint('uix_barber_day', 'barber_schedules', ['barber_id', 'day_of_week'])
    
    # Drop new columns
    op.drop_column('barber_schedules', 'updated_at')
    op.drop_column('barber_schedules', 'created_at')
    op.drop_column('barber_schedules', 'repeat_frequency')
    op.drop_column('barber_schedules', 'end_date')
    op.drop_column('barber_schedules', 'start_date')
    
    # Drop the enum type if it exists
    connection = op.get_bind()
    result = connection.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'schedulerepeatfrequency')")
    ).scalar()
    
    if result:
        op.execute("DROP TYPE schedulerepeatfrequency")
