# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""accounts: customer-assignable external account id for bulk file matching

Revision ID: c0c354b6cab5
Revises: b0c8c87126f0
Create Date: 2026-08-01 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c0c354b6cab5'
down_revision: Union[str, None] = 'b0c8c87126f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('account', sa.Column('external_account_id', sa.String(length=64), nullable=True))
    with op.batch_alter_table('account') as batch_op:
        batch_op.create_unique_constraint('uq_account_tenant_external_id', ['tenant_id', 'external_account_id'])


def downgrade() -> None:
    with op.batch_alter_table('account') as batch_op:
        batch_op.drop_constraint('uq_account_tenant_external_id', type_='unique')
    op.drop_column('account', 'external_account_id')
