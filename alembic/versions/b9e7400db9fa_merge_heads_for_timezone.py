"""merge_heads_for_timezone

Revision ID: b9e7400db9fa
Revises: 0807f1a08cea, 0b66b21e970a
Create Date: 2025-06-19 08:54:17.769292

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9e7400db9fa'
down_revision: Union[str, None] = ('0807f1a08cea', '0b66b21e970a')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
