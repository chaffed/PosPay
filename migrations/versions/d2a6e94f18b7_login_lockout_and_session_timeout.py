# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""security: login attempt lockout on user, per-tenant session timeout override

Revision ID: d2a6e94f18b7
Revises: c9f1a3d80e64
Create Date: 2026-08-14 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd2a6e94f18b7'
down_revision: Union[str, None] = 'c9f1a3d80e64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('user') as batch_op:
        batch_op.add_column(sa.Column('failed_login_attempts', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table('tenant') as batch_op:
        batch_op.add_column(sa.Column('access_token_expire_minutes', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('refresh_token_expire_minutes', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('tenant') as batch_op:
        batch_op.drop_column('refresh_token_expire_minutes')
        batch_op.drop_column('access_token_expire_minutes')

    with op.batch_alter_table('user') as batch_op:
        batch_op.drop_column('locked_until')
        batch_op.drop_column('failed_login_attempts')
