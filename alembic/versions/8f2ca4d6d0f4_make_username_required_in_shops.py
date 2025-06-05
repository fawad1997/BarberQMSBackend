"""make_username_required_in_shops

Revision ID: 8f2ca4d6d0f4
Revises: f7db13e6fc1b
Create Date: 2025-06-05 10:12:53.586432

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f2ca4d6d0f4'
down_revision: Union[str, None] = 'f7db13e6fc1b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make username column non-nullable in shops table
    # Since we've already cleaned the database, we just need to alter the column
    op.alter_column('shops', 'username',
                    existing_type=sa.String(),
                    nullable=False)


def downgrade() -> None:
    # Make username column nullable again
    op.alter_column('shops', 'username',
                    existing_type=sa.String(),
                    nullable=True)
