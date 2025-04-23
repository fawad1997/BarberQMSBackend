"""add_end_time_to_appointments

Revision ID: 0920b2ad538d
Revises: 3dcab5da49c5
Create Date: 2025-04-22 19:32:51.129979

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0920b2ad538d'
down_revision: Union[str, None] = '3dcab5da49c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add end_time column to appointments table
    op.add_column('appointments', sa.Column('end_time', sa.DateTime(), nullable=True))
    
    # Update existing appointments to set end_time based on appointment_time and service duration
    op.execute("""
        UPDATE appointments a
        SET end_time = a.appointment_time + (interval '1 minute' * (
            SELECT duration 
            FROM services s 
            WHERE s.id = a.service_id
        ))
        WHERE a.service_id IS NOT NULL
    """)


def downgrade() -> None:
    # Remove end_time column from appointments table
    op.drop_column('appointments', 'end_time')
