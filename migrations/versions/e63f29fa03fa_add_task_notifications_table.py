"""add_task_notifications_table

Revision ID: e63f29fa03fa
Revises: a60a59b000c9
Create Date: 2026-03-14 14:51:41.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e63f29fa03fa'
down_revision: Union[str, Sequence[str], None] = 'a60a59b000c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create task_notifications table for auditing follow-up emails
    op.create_table(
        'task_notifications',
        sa.Column(
            'id',
            sa.BigInteger(),
            sa.Identity(always=False, start=1, increment=1),
            nullable=False
        ),
        sa.Column(
            'task_id',
            sa.BigInteger(),
            nullable=False
        ),
        sa.Column(
            'crew_id',
            sa.BigInteger(),
            nullable=False
        ),
        sa.Column(
            'notification_type',
            sa.Text(),
            server_default='follow_up_email',
            nullable=False
        ),
        # 'sent' when email succeeded, 'failed' when it did not
        sa.Column(
            'status',
            sa.Text(),
            server_default='sent',
            nullable=False
        ),
        # Populated only on failure – contains the exception message
        sa.Column(
            'error_message',
            sa.Text(),
            nullable=True
        ),
        sa.Column(
            'sent_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False
        ),
        # FK ensures we never log a notification for a deleted task
        sa.ForeignKeyConstraint(
            ['task_id'],
            ['cleaning_tasks.id'],
            ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id')
    )

    # Index on task_id – used by _has_reached_max_notifications() and
    # _find_next_crew() to fetch all notifications for a given task quickly.
    op.create_index(
        'idx_task_notifications_task_id',
        'task_notifications',
        ['task_id']
    )

    # Index on crew_id – useful for querying a crew member's notification history.
    op.create_index(
        'idx_task_notifications_crew_id',
        'task_notifications',
        ['crew_id']
    )

    # Composite index on (task_id, crew_id) – used by _already_notified_crew()
    # which checks whether a specific (task, crew) pair was already notified.
    op.create_index(
        'idx_task_notifications_task_crew',
        'task_notifications',
        ['task_id', 'crew_id']
    )


def downgrade() -> None:
    op.drop_index('idx_task_notifications_task_crew', table_name='task_notifications')
    op.drop_index('idx_task_notifications_crew_id', table_name='task_notifications')
    op.drop_index('idx_task_notifications_task_id', table_name='task_notifications')
    op.drop_table('task_notifications')
