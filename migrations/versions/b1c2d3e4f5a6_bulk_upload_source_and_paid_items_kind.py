# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""auto-import: bulk_upload_file.source, nullable uploader, paid_items kind

Revision ID: b1c2d3e4f5a6
Revises: a3b4c5d6e7f8
Create Date: 2026-07-31 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('bulk_upload_file') as batch_op:
        # server_default must be the enum member's NAME ("MANUAL"), not its value
        # ("manual") -- see domain/bulk_upload_file.py's BulkUploadSource column and
        # migrations/versions/9327972d0952_....py's own fix for the identical bug.
        batch_op.add_column(sa.Column('source', sa.String(length=20), server_default='MANUAL', nullable=False))
        batch_op.alter_column('uploaded_by_user_id', existing_type=sa.Uuid(), nullable=True)
    # bulk_upload_kind/BulkUploadKind is stored as a plain non-native String column
    # (native_enum=False), so adding the PAID_ITEMS value is an app-level Python enum
    # change only — no schema migration needed for it.


def downgrade() -> None:
    with op.batch_alter_table('bulk_upload_file') as batch_op:
        batch_op.alter_column('uploaded_by_user_id', existing_type=sa.Uuid(), nullable=False)
        batch_op.drop_column('source')
