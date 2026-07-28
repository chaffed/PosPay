# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""extend postgres RLS defense-in-depth to webauthn credential and challenge tables

Revision ID: f48f7301f98a
Revises: 51624395f2fb
Create Date: 2026-07-22 08:01:37.495998

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f48f7301f98a'
down_revision: Union[str, None] = '51624395f2fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Same rationale as the earlier RLS migration (6b9b23b81e31): these are strictly
# single-tenant/single-user tables with no cross-tenant read path (unlike exception_item/
# decision, which the ML pipeline deliberately reads across all tenants), so RLS is safe
# to enable here without breaking anything.
_TABLES = ["webauthn_credential", "webauthn_challenge"]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table in _TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY tenant_isolation_{table} ON "{table}" '
            f"USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table in _TABLES:
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation_{table} ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
