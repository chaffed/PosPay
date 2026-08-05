# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""tenant login/banner messages + customer banner message

Revision ID: 4512815e6241
Revises: d1e2f3a4b5c6
Create Date: 2026-08-04 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4512815e6241'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Markdown source, rendered+sanitized at display time (web/templates.py::
    # render_markdown) — see domain/tenant.py and domain/customer.py's own column
    # comments. All nullable, no server_default: NULL means nothing renders, exactly the
    # right default for a brand-new column that previously didn't exist at all.
    op.add_column('tenant', sa.Column('login_message', sa.String(2000), nullable=True))
    op.add_column('tenant', sa.Column('banner_message', sa.String(2000), nullable=True))
    op.add_column('customer', sa.Column('banner_message', sa.String(2000), nullable=True))


def downgrade() -> None:
    op.drop_column('customer', 'banner_message')
    op.drop_column('tenant', 'banner_message')
    op.drop_column('tenant', 'login_message')
