# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""widen tenant/customer message columns to Text (support embedded images)

Revision ID: 333f24f85358
Revises: 4512815e6241
Create Date: 2026-08-04 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '333f24f85358'
down_revision: Union[str, None] = '4512815e6241'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Was String(2000) -- too small to hold a message with an embedded base64 image
    # (see services/message_content.py). The real size limits (150KB per image, 500KB
    # per message) are enforced in Python at save time, not by the column type; Text is
    # simply unbounded storage, same type already used for WsudStatement.
    # statement_text_snapshot.
    with op.batch_alter_table('tenant') as batch_op:
        batch_op.alter_column('login_message', type_=sa.Text(), existing_nullable=True)
        batch_op.alter_column('banner_message', type_=sa.Text(), existing_nullable=True)
    with op.batch_alter_table('customer') as batch_op:
        batch_op.alter_column('banner_message', type_=sa.Text(), existing_nullable=True)


def downgrade() -> None:
    # Truncates anything already stored beyond 2000 chars (e.g. a message with an
    # embedded image) -- an accepted, one-way lossy downgrade, same posture as this
    # app's other column-widen migrations (see b4e1c9a0d752).
    with op.batch_alter_table('customer') as batch_op:
        batch_op.alter_column('banner_message', type_=sa.String(2000), existing_nullable=True)
    with op.batch_alter_table('tenant') as batch_op:
        batch_op.alter_column('banner_message', type_=sa.String(2000), existing_nullable=True)
        batch_op.alter_column('login_message', type_=sa.String(2000), existing_nullable=True)
