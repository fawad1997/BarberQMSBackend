"""merge_heads_before_refactor

Revision ID: a48998887701
Revises: 0807f1a08cea, 0b66b21e970a
Create Date: 2025-06-18 23:14:43.710561

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a48998887701'
down_revision: Union[str, None] = ('0807f1a08cea', '0b66b21e970a')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
