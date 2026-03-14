"""add_category_id_to_cleaning_tasks

Revision ID: 9a67e68fb6a6
Revises: e63f29fa03fa
Create Date: 2026-03-14 17:56:19.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9a67e68fb6a6'
down_revision: Union[str, Sequence[str], None] = 'e63f29fa03fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add category_id column (nullable initially for backfill)
    op.add_column('cleaning_tasks', sa.Column('category_id', sa.BigInteger(), nullable=True))
    
    # 2. Add foreign key index/constraint
    op.create_foreign_key(
        'fk_cleaning_tasks_category_id',
        'cleaning_tasks', 'service_category',
        ['category_id'], ['id']
    )
    
    # 3. Backfill category_id from cleaning_crews table
    # We join cleaning_tasks with cleaning_crews on crew_id to find the correct category_id
    op.execute("""
        UPDATE cleaning_tasks ct
        SET category_id = cc.category_id
        FROM cleaning_crews cc
        WHERE ct.crew_id = cc.id
          AND ct.category_id IS NULL
    """)

def downgrade() -> None:
    op.drop_constraint('fk_cleaning_tasks_category_id', 'cleaning_tasks', type_='foreignkey')
    op.drop_column('cleaning_tasks', 'category_id')
