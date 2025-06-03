"""merge work schedules heads

Revision ID: merge_work_schedules_heads
Revises: update_timestamps_timezone, 20240319_create_work_schedules
Create Date: 2024-03-19 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'merge_work_schedules_heads'
down_revision = ('update_timestamps_timezone', '20240319_create_work_schedules')
branch_labels = None
depends_on = None

def upgrade():
    pass

def downgrade():
    pass 