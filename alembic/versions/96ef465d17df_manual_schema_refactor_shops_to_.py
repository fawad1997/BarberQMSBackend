"""manual_schema_refactor_shops_to_businesses

Revision ID: 96ef465d17df
Revises: a48998887701
Create Date: 2025-06-18 23:14:57.468136

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '96ef465d17df'
down_revision: Union[str, None] = 'a48998887701'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # First, let's update enum types
    
    # Create new enum for EmployeeStatus (similar to BarberStatus)
    op.execute("CREATE TYPE employeestatus AS ENUM ('available', 'in_service', 'on_break', 'off')")
    
    # Create new enum for OverrideType
    op.execute("CREATE TYPE overridetype AS ENUM ('holiday', 'special_event', 'emergency', 'personal', 'sick_leave')")
    
    # 1. Rename shops table to businesses
    op.rename_table('shops', 'businesses')
    
    # 2. Add new columns to businesses table
    op.add_column('businesses', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('businesses', sa.Column('logo_url', sa.String(), nullable=True))
    op.add_column('businesses', sa.Column('is_open_24_hours', sa.Boolean(), default=False))
    
    # Remove old columns from businesses (formerly shops)
    # Note: We'll keep opening_time and closing_time for now to avoid data loss
    # They can be removed later after migrating to business_operating_hours
    
    # 3. Rename barbers table to employees
    op.rename_table('barbers', 'employees')
    
    # 4. Update column references in employees table
    op.alter_column('employees', 'shop_id', new_column_name='business_id')
    
    # 5. Update status column in employees table to use new enum
    op.execute("ALTER TABLE employees ALTER COLUMN status TYPE employeestatus USING status::text::employeestatus")
    
    # 6. Rename barber_services table to employee_services
    op.rename_table('barber_services', 'employee_services')
    op.alter_column('employee_services', 'barber_id', new_column_name='employee_id')
    
    # 7. Update appointments table
    op.alter_column('appointments', 'shop_id', new_column_name='business_id')
    op.alter_column('appointments', 'barber_id', new_column_name='employee_id')
    
    # Add new columns to appointments
    op.add_column('appointments', sa.Column('total_duration', sa.Integer(), nullable=True))
    op.add_column('appointments', sa.Column('total_price', sa.Float(), nullable=True))
    op.add_column('appointments', sa.Column('notes', sa.Text(), nullable=True))
    
    # 8. Update queue_entries table
    op.alter_column('queue_entries', 'shop_id', new_column_name='business_id')
    op.alter_column('queue_entries', 'barber_id', new_column_name='employee_id')
    
    # Add new columns to queue_entries
    op.add_column('queue_entries', sa.Column('estimated_service_time', sa.DateTime(timezone=True), nullable=True))
    op.add_column('queue_entries', sa.Column('notes', sa.Text(), nullable=True))
    
    # 9. Update feedbacks table
    op.alter_column('feedbacks', 'shop_id', new_column_name='business_id')
    op.alter_column('feedbacks', 'barber_id', new_column_name='employee_id')
    op.alter_column('feedbacks', 'comments', new_column_name='message')
    
    # Add new columns to feedbacks
    op.add_column('feedbacks', sa.Column('subject', sa.String(), nullable=True))
    
    # 10. Update services table
    op.alter_column('services', 'shop_id', new_column_name='business_id')
    
    # Add new columns to services
    op.add_column('services', sa.Column('is_active', sa.Boolean(), default=True))
    op.add_column('services', sa.Column('category', sa.String(), nullable=True))
    
    # 11. Create new business_operating_hours table
    op.create_table('business_operating_hours',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('business_id', sa.Integer(), sa.ForeignKey('businesses.id'), nullable=False),
        sa.Column('day_of_week', sa.Integer(), nullable=False),  # 0=Sunday, 1=Monday, ..., 6=Saturday
        sa.Column('opening_time', sa.Time(), nullable=True),
        sa.Column('closing_time', sa.Time(), nullable=True),
        sa.Column('is_closed', sa.Boolean(), default=False),
        sa.Column('lunch_break_start', sa.Time(), nullable=True),
        sa.Column('lunch_break_end', sa.Time(), nullable=True),
        sa.UniqueConstraint('business_id', 'day_of_week', name='uix_business_day')
    )
    
    # 12. Rename barber_schedules to employee_schedules and restructure
    op.rename_table('barber_schedules', 'employee_schedules')
    op.alter_column('employee_schedules', 'barber_id', new_column_name='employee_id')
    
    # Drop old columns that don't fit the new day-based model
    try:
        op.drop_column('employee_schedules', 'start_date')
    except:
        pass
    try:
        op.drop_column('employee_schedules', 'end_date')
    except:
        pass
    try:
        op.drop_column('employee_schedules', 'repeat_frequency')
    except:
        pass
    
    # Add new columns for day-based scheduling
    try:
        op.add_column('employee_schedules', sa.Column('day_of_week', sa.Integer(), nullable=False, default=0))
    except:
        pass
    try:
        op.add_column('employee_schedules', sa.Column('start_time', sa.Time(), nullable=True))
    except:
        pass
    try:
        op.add_column('employee_schedules', sa.Column('end_time', sa.Time(), nullable=True))
    except:
        pass
    try:
        op.add_column('employee_schedules', sa.Column('lunch_break_start', sa.Time(), nullable=True))
    except:
        pass
    try:
        op.add_column('employee_schedules', sa.Column('lunch_break_end', sa.Time(), nullable=True))
    except:
        pass
    try:
        op.add_column('employee_schedules', sa.Column('is_working', sa.Boolean(), default=True))
    except:
        pass
    
    # Add unique constraint
    try:
        op.create_unique_constraint('uix_employee_day', 'employee_schedules', ['employee_id', 'day_of_week'])
    except:
        pass
    
    # 13. Update schedule_overrides table
    try:
        op.alter_column('schedule_overrides', 'barber_id', new_column_name='employee_id')
    except:
        pass
    try:
        op.alter_column('schedule_overrides', 'shop_id', new_column_name='business_id')
    except:
        pass
    
    # Add new columns to schedule_overrides
    try:
        op.add_column('schedule_overrides', sa.Column('reason', sa.String(), nullable=True))
    except:
        pass
    try:
        op.add_column('schedule_overrides', sa.Column('override_type', sa.Enum('holiday', 'special_event', 'emergency', 'personal', 'sick_leave', name='overridetype'), nullable=True))
    except:
        pass
    
    # 14. Create new business_advertisements table
    try:
        op.create_table('business_advertisements',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('business_id', sa.Integer(), sa.ForeignKey('businesses.id'), nullable=False),
            sa.Column('image_url', sa.String(), nullable=False),
            sa.Column('start_date', sa.DateTime(), nullable=False),
            sa.Column('end_date', sa.DateTime(), nullable=False),
            sa.Column('is_active', sa.Boolean(), default=True),
            sa.Column('created_at', sa.DateTime(), default=sa.func.now())
        )
    except:
        pass
    
    # 15. Create new contact_messages table
    try:
        op.create_table('contact_messages',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('subject', sa.String(), nullable=False),
            sa.Column('message', sa.Text(), nullable=False),
            sa.Column('email', sa.String(), nullable=True),
            sa.Column('phone_number', sa.String(), nullable=True),
            sa.Column('created_at', sa.DateTime(), default=sa.func.now())
        )
    except:
        pass
    
    # 16. Update foreign key constraints (with error handling)
    # Drop old foreign keys if they exist
    constraints_to_drop = [
        ('employees_shop_id_fkey', 'employees'),
        ('employee_services_barber_id_fkey', 'employee_services'),
        ('appointments_shop_id_fkey', 'appointments'),
        ('appointments_barber_id_fkey', 'appointments'),
        ('queue_entries_shop_id_fkey', 'queue_entries'),
        ('queue_entries_barber_id_fkey', 'queue_entries'),
        ('feedbacks_shop_id_fkey', 'feedbacks'),
        ('feedbacks_barber_id_fkey', 'feedbacks'),
        ('services_shop_id_fkey', 'services'),
        ('employee_schedules_barber_id_fkey', 'employee_schedules'),
        ('schedule_overrides_barber_id_fkey', 'schedule_overrides'),
        ('schedule_overrides_shop_id_fkey', 'schedule_overrides'),
    ]
    
    for constraint_name, table_name in constraints_to_drop:
        try:
            op.drop_constraint(constraint_name, table_name, type_='foreignkey')
        except:
            # Constraint might not exist or have a different name
            pass
    
    # Create new foreign keys if they don't exist
    foreign_keys_to_create = [
        ('employees_business_id_fkey', 'employees', 'businesses', ['business_id'], ['id']),
        ('employee_services_employee_id_fkey', 'employee_services', 'employees', ['employee_id'], ['id']),
        ('appointments_business_id_fkey', 'appointments', 'businesses', ['business_id'], ['id']),
        ('appointments_employee_id_fkey', 'appointments', 'employees', ['employee_id'], ['id']),
        ('queue_entries_business_id_fkey', 'queue_entries', 'businesses', ['business_id'], ['id']),
        ('queue_entries_employee_id_fkey', 'queue_entries', 'employees', ['employee_id'], ['id']),
        ('feedbacks_business_id_fkey', 'feedbacks', 'businesses', ['business_id'], ['id']),
        ('feedbacks_employee_id_fkey', 'feedbacks', 'employees', ['employee_id'], ['id']),
        ('services_business_id_fkey', 'services', 'businesses', ['business_id'], ['id']),
        ('schedule_overrides_employee_id_fkey', 'schedule_overrides', 'employees', ['employee_id'], ['id']),
        ('schedule_overrides_business_id_fkey', 'schedule_overrides', 'businesses', ['business_id'], ['id']),
    ]
    
    for constraint_name, source_table, target_table, source_columns, target_columns in foreign_keys_to_create:
        try:
            op.create_foreign_key(constraint_name, source_table, target_table, source_columns, target_columns)
        except:
            # Constraint might already exist
            pass
    
    # Special case for employee_schedules with CASCADE delete
    try:
        op.create_foreign_key('employee_schedules_employee_id_fkey', 'employee_schedules', 'employees', ['employee_id'], ['id'], ondelete='CASCADE')
    except:
        pass


def downgrade() -> None:
    # Note: This is a complex migration, downgrade would be very involved
    # For now, we'll leave this empty as this is a one-way migration
    # In production, you might want to implement a proper downgrade
    pass
