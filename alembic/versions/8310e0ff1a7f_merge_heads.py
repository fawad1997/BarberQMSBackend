"""merge heads

Revision ID: 8310e0ff1a7f
Revises: add_username_to_shops, merge_work_schedules_heads
Create Date: 2025-06-04 22:20:26.170382

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8310e0ff1a7f'
down_revision: Union[str, None] = ('add_username_to_shops', 'merge_work_schedules_heads')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
