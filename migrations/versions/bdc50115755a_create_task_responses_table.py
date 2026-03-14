"""create_task_responses_table

Revision ID: bdc50115755a
Revises: e9ba689d7696
Create Date: 2026-03-14 18:03:54.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func

# revision identifiers, used by Alembic.
revision: str = 'bdc50115755a'
down_revision: Union[str, Sequence[str], None] = 'e9ba689d7696'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create task_responses table
    op.create_table(
        'task_responses',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False, start=1, increment=1), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('task_id', sa.Text(), nullable=False),
        sa.Column('task_type', sa.Text(), nullable=False),
        sa.Column('response', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create index on task_id for efficient lookups by cron job
    op.create_index('idx_task_responses_task_id', 'task_responses', ['task_id'])

def downgrade() -> None:
    op.drop_index('idx_task_responses_task_id', table_name='task_responses')
    op.drop_table('task_responses')
