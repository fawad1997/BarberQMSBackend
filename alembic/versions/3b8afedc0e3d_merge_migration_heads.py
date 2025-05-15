"""merge_migration_heads

Revision ID: 3b8afedc0e3d
Revises: ee20217de0b5, update_timestamps_timezone
Create Date: 2025-05-14 00:54:55.521094

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3b8afedc0e3d'
down_revision: Union[str, None] = ('ee20217de0b5', 'update_timestamps_timezone')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
