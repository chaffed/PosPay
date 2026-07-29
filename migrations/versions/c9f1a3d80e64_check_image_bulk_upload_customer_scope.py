# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""security: add customer_id scoping to check_image and bulk_upload_file

Revision ID: c9f1a3d80e64
Revises: b4e1c9a0d752
Create Date: 2026-08-10 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9f1a3d80e64'
down_revision: Union[str, None] = 'b4e1c9a0d752'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("check_image", "bulk_upload_file")


def upgrade() -> None:
    # Nullable, no backfill — existing rows just become bank-wide-visible
    # (customer_id=None), which is only ever a widening of who can see them today, never
    # a new restriction (repositories/base.py::CustomerScopedRepository's own semantics).
    for table_name in _TABLES:
        op.add_column(table_name, sa.Column('customer_id', sa.Uuid(), nullable=True))
        op.create_index(op.f(f'ix_{table_name}_customer_id'), table_name, ['customer_id'], unique=False)
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_foreign_key(
                op.f(f'fk_{table_name}_customer_id_customer'), 'customer', ['customer_id'], ['id']
            )


def downgrade() -> None:
    for table_name in _TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(op.f(f'fk_{table_name}_customer_id_customer'), type_='foreignkey')
        op.drop_index(op.f(f'ix_{table_name}_customer_id'), table_name=table_name)
        op.drop_column(table_name, 'customer_id')
