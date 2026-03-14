"""add_status_column_to_cleaning_tasks

Revision ID: e9ba689d7696
Revises: 9a67e68fb6a6
Create Date: 2026-03-14 17:58:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e9ba689d7696'
down_revision: Union[str, Sequence[str], None] = '9a67e68fb6a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add status column to cleaning_tasks (defaults to pending)
    op.add_column('cleaning_tasks', sa.Column('status', sa.Text(), server_default='pending', nullable=False))
    
    # 2. Backfill existing tasks to 'pending' if they were null (server_default takes care of new ones, 
    # but existing ones might need explicit update if server_default wasn't applied to existing rows)
    op.execute("UPDATE cleaning_tasks SET status = 'pending' WHERE status IS NULL")

def downgrade() -> None:
    op.drop_column('cleaning_tasks', 'status')
