"""create work schedules tables

Revision ID: 20240319_create_work_schedules
Revises: update_timestamps_timezone
Create Date: 2024-03-19 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

# revision identifiers, used by Alembic.
revision = '20240319_create_work_schedules'
down_revision = 'update_timestamps_timezone'
branch_labels = None
depends_on = None

def upgrade():
    # Create work_schedules table
    op.create_table(
        'work_schedules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('day_of_week', ARRAY(sa.Integer()), nullable=True),
        sa.Column('start_time', sa.Time(), nullable=True),
        sa.Column('end_time', sa.Time(), nullable=True),
        sa.Column('effective_start_date', sa.Date(), nullable=True),
        sa.Column('effective_end_date', sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_work_schedules_id'), 'work_schedules', ['id'], unique=False)

    # Create schedule_breaks table
    op.create_table(
        'schedule_breaks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('work_schedule_id', sa.Integer(), nullable=False),
        sa.Column('break_start', sa.Time(), nullable=True),
        sa.Column('break_end', sa.Time(), nullable=True),
        sa.ForeignKeyConstraint(['work_schedule_id'], ['work_schedules.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_schedule_breaks_id'), 'schedule_breaks', ['id'], unique=False)

    # Create employee_schedules table
    op.create_table(
        'employee_schedules',
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('work_schedule_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['barbers.id'], ),
        sa.ForeignKeyConstraint(['work_schedule_id'], ['work_schedules.id'], ),
        sa.PrimaryKeyConstraint('employee_id', 'work_schedule_id')
    )

    # Create schedule_overrides table
    op.create_table(
        'schedule_overrides',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('barber_id', sa.Integer(), nullable=True),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('end_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('repeat_frequency', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['barber_id'], ['barbers.id'], ),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_schedule_overrides_id'), 'schedule_overrides', ['id'], unique=False)

def downgrade():
    op.drop_index(op.f('ix_schedule_overrides_id'), table_name='schedule_overrides')
    op.drop_table('schedule_overrides')
    op.drop_table('employee_schedules')
    op.drop_index(op.f('ix_schedule_breaks_id'), table_name='schedule_breaks')
    op.drop_table('schedule_breaks')
    op.drop_index(op.f('ix_work_schedules_id'), table_name='work_schedules')
    op.drop_table('work_schedules') 