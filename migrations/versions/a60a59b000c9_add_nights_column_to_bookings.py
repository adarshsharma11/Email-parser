"""add nights column to bookings

Revision ID: a60a59b000c9
Revises: 6f66cbc2371c
Create Date: 2026-03-13 12:34:05.215859

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a60a59b000c9'
down_revision: Union[str, Sequence[str], None] = '6f66cbc2371c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('bookings', sa.Column('nights', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('bookings', 'nights')
