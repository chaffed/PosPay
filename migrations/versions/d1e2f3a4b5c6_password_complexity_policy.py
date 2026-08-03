# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""password complexity policy: tenant baseline + customer additive override

Revision ID: d1e2f3a4b5c6
Revises: b2c3d4e5f6a7
Create Date: 2026-08-01 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tenant's own baseline policy — permissive defaults (min length 8, no complexity
    # required) so no existing password anywhere is retroactively invalidated; this is
    # only ever checked at account-creation time (services/user_service.py::
    # create_user_with_membership), never against a password already set.
    op.add_column('tenant', sa.Column('password_min_length', sa.Integer(), nullable=False, server_default='8'))
    op.add_column('tenant', sa.Column('password_require_uppercase', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('tenant', sa.Column('password_require_lowercase', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('tenant', sa.Column('password_require_number', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('tenant', sa.Column('password_require_symbol', sa.Boolean(), nullable=False, server_default=sa.false()))

    # Customer's own ADDITIONAL requirements on top of the tenant's — NULL/false means
    # "no extra requirement, just use the tenant's" (see auth/password_policy.py). No
    # server_default needed for password_min_length: NULL is exactly the right default.
    op.add_column('customer', sa.Column('password_min_length', sa.Integer(), nullable=True))
    op.add_column('customer', sa.Column('password_require_uppercase', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('customer', sa.Column('password_require_lowercase', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('customer', sa.Column('password_require_number', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('customer', sa.Column('password_require_symbol', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('customer', 'password_require_symbol')
    op.drop_column('customer', 'password_require_number')
    op.drop_column('customer', 'password_require_lowercase')
    op.drop_column('customer', 'password_require_uppercase')
    op.drop_column('customer', 'password_min_length')

    op.drop_column('tenant', 'password_require_symbol')
    op.drop_column('tenant', 'password_require_number')
    op.drop_column('tenant', 'password_require_lowercase')
    op.drop_column('tenant', 'password_require_uppercase')
    op.drop_column('tenant', 'password_min_length')
