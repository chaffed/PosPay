# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""exception_item: fraud training example provenance (source, is_correction, retraction)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-05 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('exception_item') as batch_op:
        # server_default must be the enum member's NAME ("LIVE"), not its value ("live")
        # -- see domain/exception_item.py's ExceptionItemSource column and
        # migrations/versions/9327972d0952_....py's own fix for the identical bug.
        batch_op.add_column(
            sa.Column('source', sa.String(length=20), nullable=False, server_default='LIVE')
        )
        batch_op.add_column(
            sa.Column('is_correction', sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column('retracted_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column('retracted_by_user_id', sa.Uuid(), sa.ForeignKey('user.id'), nullable=True)
        )
    # 'fraud_training_examples' (23 chars) doesn't fit the old length=20 bound.
    with op.batch_alter_table('bulk_upload_file') as batch_op:
        batch_op.alter_column('kind', existing_type=sa.String(length=20), type_=sa.String(length=30))


def downgrade() -> None:
    with op.batch_alter_table('bulk_upload_file') as batch_op:
        batch_op.alter_column('kind', existing_type=sa.String(length=30), type_=sa.String(length=20))
    with op.batch_alter_table('exception_item') as batch_op:
        batch_op.drop_column('retracted_by_user_id')
        batch_op.drop_column('retracted_at')
        batch_op.drop_column('is_correction')
        batch_op.drop_column('source')
