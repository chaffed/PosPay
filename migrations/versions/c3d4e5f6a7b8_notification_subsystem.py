# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""notifications: notification + notification_preference tables, user.phone

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
Create Date: 2026-08-01 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# `notification` deliberately gets NO row-level-security policy, same reasoning as the
# `user` table's own RLS exclusion (see ba635450e77c): its tenant_id is nullable
# (ACCOUNT_LOCKED/ACCOUNT_UNLOCKED are about the User identity, not any one tenant) and
# it's never read scoped to one tenant's session context in the first place -- it's only
# ever written by trusted service code that already knows the right tenant_id, and drained
# across every tenant at once by the background dispatch job, the same cross-tenant access
# pattern that already justifies excluding `user` itself.


def upgrade() -> None:
    op.add_column('user', sa.Column('phone', sa.String(length=32), nullable=True))

    op.create_table(
        'notification',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=True),
        sa.Column('recipient_user_id', sa.Uuid(), nullable=False),
        sa.Column(
            'notification_type',
            sa.Enum(
                'EXCEPTION_CREATED', 'RECOMMENDATION_AWAITING_APPROVAL', 'ACCOUNT_LOCKED', 'ACCOUNT_UNLOCKED',
                name='notification_type', native_enum=False, length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            'channel',
            sa.Enum('EMAIL', 'SMS', name='notification_channel', native_enum=False, length=10),
            nullable=False,
        ),
        sa.Column('destination', sa.String(length=255), nullable=False),
        sa.Column('subject', sa.String(length=255), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('resource_type', sa.String(length=50), nullable=True),
        sa.Column('resource_id', sa.Uuid(), nullable=True),
        sa.Column(
            'status',
            sa.Enum('PENDING', 'SENT', 'FAILED', name='notification_status', native_enum=False, length=10),
            nullable=False,
            server_default='PENDING',
        ),
        sa.Column('error', sa.String(length=1000), nullable=True),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name=op.f('fk_notification_tenant_id_tenant')),
        sa.ForeignKeyConstraint(['recipient_user_id'], ['user.id'], name=op.f('fk_notification_recipient_user_id_user')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_notification')),
    )
    op.create_index(op.f('ix_notification_tenant_id'), 'notification', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_notification_recipient_user_id'), 'notification', ['recipient_user_id'], unique=False)
    # The dispatch job's own query shape: oldest-first PENDING rows.
    op.create_index('ix_notification_status_created_at', 'notification', ['status', 'created_at'], unique=False)

    op.create_table(
        'notification_preference',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column(
            'notification_type',
            sa.Enum(
                'EXCEPTION_CREATED', 'RECOMMENDATION_AWAITING_APPROVAL', 'ACCOUNT_LOCKED', 'ACCOUNT_UNLOCKED',
                name='notification_type', native_enum=False, length=40,
            ),
            nullable=False,
        ),
        sa.Column('email_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('sms_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_notification_preference_user_id_user')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_notification_preference')),
        sa.UniqueConstraint('user_id', 'notification_type', name='uq_notification_pref_user_type'),
    )
    op.create_index(op.f('ix_notification_preference_user_id'), 'notification_preference', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_notification_preference_user_id'), table_name='notification_preference')
    op.drop_table('notification_preference')

    op.drop_index('ix_notification_status_created_at', table_name='notification')
    op.drop_index(op.f('ix_notification_recipient_user_id'), table_name='notification')
    op.drop_index(op.f('ix_notification_tenant_id'), table_name='notification')
    op.drop_table('notification')

    op.drop_column('user', 'phone')
