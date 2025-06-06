"""update_schedule_override_repeat_frequency

Revision ID: update_schedule_override_repeat_frequency
Revises: fff50fee97e4
Create Date: 2024-04-30 03:10:05.535626

"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'update_schedule_override_repeat_frequency'
down_revision: Union[str, None] = 'fff50fee97e4'
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
    
    # Add a temporary column with the new type
    op.add_column('schedule_overrides', sa.Column('repeat_frequency_new', sa.Enum('NONE', 'DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY', name='schedulerepeatfrequency'), nullable=True))
    
    # Copy and convert data from the old column to the new one
    connection.execute(
        sa.text("""
            UPDATE schedule_overrides 
            SET repeat_frequency_new = CASE 
                WHEN repeat_frequency IS NULL THEN 'NONE'::schedulerepeatfrequency
                WHEN UPPER(repeat_frequency) = 'DAILY' THEN 'DAILY'::schedulerepeatfrequency
                WHEN UPPER(repeat_frequency) = 'WEEKLY' THEN 'WEEKLY'::schedulerepeatfrequency
                WHEN UPPER(repeat_frequency) = 'MONTHLY' THEN 'MONTHLY'::schedulerepeatfrequency
                WHEN UPPER(repeat_frequency) = 'YEARLY' THEN 'YEARLY'::schedulerepeatfrequency
                ELSE 'NONE'::schedulerepeatfrequency
            END
        """)
    )
    
    # Drop the old column and rename the new one
    op.drop_column('schedule_overrides', 'repeat_frequency')
    op.alter_column('schedule_overrides', 'repeat_frequency_new', new_column_name='repeat_frequency')
    
    # Make the column non-nullable with a default value
    op.alter_column('schedule_overrides', 'repeat_frequency',
                    nullable=False,
                    server_default='NONE')


def downgrade() -> None:
    # Convert back to string column
    op.alter_column('schedule_overrides', 'repeat_frequency',
                    type_=sa.String(),
                    postgresql_using="repeat_frequency::text",
                    nullable=True)
    
    # Drop the enum type if it exists
    connection = op.get_bind()
    result = connection.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'schedulerepeatfrequency')")
    ).scalar()
    
    if result:
        op.execute("DROP TYPE schedulerepeatfrequency") 