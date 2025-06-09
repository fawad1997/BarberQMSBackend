"""merge_is_first_login_with_main

Revision ID: 6cbf0a1b20f6
Revises: 0807f1a08cea, 0b66b21e970a
Create Date: 2025-06-09 23:04:42.291298

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6cbf0a1b20f6'
down_revision: Union[str, None] = ('0807f1a08cea', '0b66b21e970a')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
