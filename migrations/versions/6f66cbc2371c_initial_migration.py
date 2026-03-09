"""initial_migration

Revision ID: 6f66cbc2371c
Revises: 
Create Date: 2026-02-24 18:32:16.048028

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '6f66cbc2371c'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        'users',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False, start=1, increment=1), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('first_name', sa.Text(), nullable=True),
        sa.Column('last_name', sa.Text(), nullable=True),
        sa.Column('email', sa.Text(), nullable=True),
        sa.Column('password', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # 2. user_credentials
    op.create_table(
        'user_credentials',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False, start=1, increment=1), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('email', sa.Text(), nullable=True),
        sa.Column('password', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.Text(), server_default='inactive', nullable=True),
        sa.Column('platform', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # 3. category
    op.create_table(
        'category',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False, start=1, increment=1), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('parent_id', sa.BigInteger(), nullable=True),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # 4. service_category
    op.create_table(
        'service_category',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False, start=1, increment=1), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('category_name', sa.Text(), nullable=True),
        sa.Column('time', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.Boolean(), server_default='true', nullable=True),
        sa.Column('price', sa.Numeric(), nullable=True),
        sa.Column('email', sa.Text(), nullable=True),
        sa.Column('phone', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # 5. properties
    op.create_table(
        'properties',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False, start=1, increment=1), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('vrbo_id', sa.Text(), nullable=True),
        sa.Column('airbnb_id', sa.Text(), nullable=True),
        sa.Column('booking_id', sa.Text(), nullable=True),
        sa.Column('ical_feed_url', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # 6. cleaning_crews
    op.create_table(
        'cleaning_crews',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False, start=1, increment=1), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('phone', sa.Text(), nullable=True),
        sa.Column('email', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=True),
        sa.Column('property_id', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('category_id', sa.BigInteger(), nullable=True),
        sa.Column('role', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # 7. cleaning_tasks
    op.create_table(
        'cleaning_tasks',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False, start=1, increment=1), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('reservation_id', sa.Text(), nullable=True),
        sa.Column('property_id', sa.Text(), nullable=True),
        sa.Column('scheduled_date', sa.DateTime(), nullable=True),
        sa.Column('crew_id', sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(['crew_id'], ['cleaning_crews.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # 8. bookings
    op.create_table(
        'bookings',
        sa.Column('reservation_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('platform', sa.Text(), nullable=True),
        sa.Column('guest_name', sa.Text(), nullable=True),
        sa.Column('guest_phone', sa.Text(), nullable=True),
        sa.Column('guest_email', sa.Text(), nullable=True),
        sa.Column('check_in_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('check_out_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('property_id', sa.Text(), nullable=True),
        sa.Column('property_name', sa.Text(), nullable=True),
        sa.Column('number_of_guests', sa.Integer(), nullable=True),
        sa.Column('total_amount', sa.Float(), nullable=True),
        sa.Column('currency', sa.Text(), nullable=True),
        sa.Column('booking_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('email_id', sa.Text(), nullable=True),
        sa.Column('raw_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('reservation_id')
    )

    # 9. booking_service
    op.create_table(
        'booking_service',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False, start=1, increment=1), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('booking_id', sa.Text(), nullable=True),
        sa.Column('service_id', sa.BigInteger(), nullable=True),
        sa.Column('service_date', sa.Date(), nullable=True),
        sa.Column('time', sa.Time(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # 10. activity_rule
    op.create_table(
        'activity_rule',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False, start=1, increment=1), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('rule_name', sa.Text(), nullable=True),
        sa.Column('condition', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('priority', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.Boolean(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('slug_name', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # 11. activity_rule_log
    op.create_table(
        'activity_rule_log',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False, start=1, increment=1), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rule_name', sa.Text(), nullable=True),
        sa.Column('outcome', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('activity_rule_log')
    op.drop_table('activity_rule')
    op.drop_table('booking_service')
    op.drop_table('bookings')
    op.drop_table('cleaning_tasks')
    op.drop_table('cleaning_crews')
    op.drop_table('properties')
    op.drop_table('service_category')
    op.drop_table('category')
    op.drop_table('user_credentials')
    op.drop_table('users')
