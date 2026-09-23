# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""security: server-side session revocation (per-user token version, revoked sessions)

Revision ID: f2a9d4c7e1b3
Revises: e8f1c2a4b6d0
Create Date: 2026-09-22 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2a9d4c7e1b3'
down_revision: Union[str, None] = 'e8f1c2a4b6d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('user') as batch_op:
        batch_op.add_column(sa.Column('token_version', sa.Integer(), nullable=False, server_default='0'))

    op.create_table(
        'revoked_session',
        sa.Column('session_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('session_id'),
    )
    op.create_index('ix_revoked_session_user_id', 'revoked_session', ['user_id'])
    op.create_index('ix_revoked_session_expires_at', 'revoked_session', ['expires_at'])


def downgrade() -> None:
    op.drop_index('ix_revoked_session_expires_at', table_name='revoked_session')
    op.drop_index('ix_revoked_session_user_id', table_name='revoked_session')
    op.drop_table('revoked_session')

    with op.batch_alter_table('user') as batch_op:
        batch_op.drop_column('token_version')
