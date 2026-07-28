# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""tenant_membership: require_webauthn override for password login despite SSO

Revision ID: a7d4f0e29c31
Revises: f3a8b6e21c40
Create Date: 2026-08-06 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7d4f0e29c31'
down_revision: Union[str, None] = 'f3a8b6e21c40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tenant_membership') as batch_op:
        batch_op.add_column(sa.Column('require_webauthn', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table('tenant_membership') as batch_op:
        batch_op.drop_column('require_webauthn')
