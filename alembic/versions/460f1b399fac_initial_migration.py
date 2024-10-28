"""Initial migration

Revision ID: 460f1b399fac
Revises: 794c2bc651c6
Create Date: 2024-10-28 01:40:10.960016

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '460f1b399fac'
down_revision: Union[str, None] = '794c2bc651c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
