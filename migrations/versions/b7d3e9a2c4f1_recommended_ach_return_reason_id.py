# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""exceptions: store the maker's chosen ACH return reason as a foreign key

Revision ID: b7d3e9a2c4f1
Revises: a9c4e2f1d7b5
Create Date: 2026-09-23 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7d3e9a2c4f1'
down_revision: Union[str, None] = 'a9c4e2f1d7b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing recommendations keep working through the old text match (see
    # web/routers/exceptions.py::exception_detail), so there's nothing to backfill.
    with op.batch_alter_table('exception_item') as batch_op:
        batch_op.add_column(sa.Column('recommended_ach_return_reason_id', sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            'fk_exception_item_recommended_ach_return_reason', 'ach_return_reason', ['recommended_ach_return_reason_id'], ['id']
        )


def downgrade() -> None:
    with op.batch_alter_table('exception_item') as batch_op:
        batch_op.drop_constraint('fk_exception_item_recommended_ach_return_reason', type_='foreignkey')
        batch_op.drop_column('recommended_ach_return_reason_id')
