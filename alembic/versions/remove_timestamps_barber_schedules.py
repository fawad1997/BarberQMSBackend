"""Remove timestamps from barber schedules

Revision ID: 8a9b2c3d4e
Revises: fff50fee97e4
Create Date: 2024-04-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8a9b2c3d4e'
down_revision: Union[str, None] = 'fff50fee97e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Drop the created_at and updated_at columns
    op.drop_column('barber_schedules', 'created_at')
    op.drop_column('barber_schedules', 'updated_at')

def downgrade() -> None:
    # Add back the created_at and updated_at columns
    op.add_column('barber_schedules', sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True))
    op.add_column('barber_schedules', sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True)) 