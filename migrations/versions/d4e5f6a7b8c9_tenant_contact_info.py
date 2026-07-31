# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""tenant: contact info fields for the page footer

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-02 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tenant') as batch_op:
        batch_op.add_column(sa.Column('support_email', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('support_phone', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('website', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('address_line1', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('address_line2', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('city', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('state', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('postal_code', sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('tenant') as batch_op:
        batch_op.drop_column('postal_code')
        batch_op.drop_column('state')
        batch_op.drop_column('city')
        batch_op.drop_column('address_line2')
        batch_op.drop_column('address_line1')
        batch_op.drop_column('website')
        batch_op.drop_column('support_phone')
        batch_op.drop_column('support_email')
