"""merge_all_heads

Revision ID: 0b66b21e970a
Revises: b4c5d8019e25, merge_work_schedules_heads, abcd1234efgh
Create Date: 2025-06-06 23:37:10.704926

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0b66b21e970a'
down_revision: Union[str, None] = ('b4c5d8019e25', 'merge_work_schedules_heads', 'abcd1234efgh')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
