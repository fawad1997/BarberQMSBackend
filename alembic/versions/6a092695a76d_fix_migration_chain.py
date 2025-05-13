"""fix_migration_chain

Revision ID: 6a092695a76d
Revises: 8a9b2c3d4e
Create Date: 2025-05-01 00:23:15.551558

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6a092695a76d'
down_revision: Union[str, None] = '8a9b2c3d4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
