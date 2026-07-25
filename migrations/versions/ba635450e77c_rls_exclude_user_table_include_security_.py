"""RLS: exclude user table, include security_group and tenant_membership

Revision ID: ba635450e77c
Revises: 23275a18351d
Create Date: 2026-07-24 15:33:09.758445

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ba635450e77c'
down_revision: Union[str, None] = '23275a18351d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# `user` is now a global identity table (see 23275a18351d) with no tenant_id column at
# all, so a per-tenant RLS policy no longer applies to it — access to a given tenant is
# governed by tenant_membership, not by filtering rows on `user` itself. This is the same
# kind of deliberate, documented RLS exclusion as exception_item/decision (see
# 6b9b23b81e31): `user` legitimately has no single-tenant row-ownership story anymore.
_NEW_TENANT_SCOPED_TABLES = ["security_group", "tenant_membership"]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute('DROP POLICY IF EXISTS tenant_isolation_user ON "user"')
    op.execute('ALTER TABLE "user" NO FORCE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "user" DISABLE ROW LEVEL SECURITY')

    for table in _NEW_TENANT_SCOPED_TABLES:
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

    for table in _NEW_TENANT_SCOPED_TABLES:
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation_{table} ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')

    op.execute('ALTER TABLE "user" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "user" FORCE ROW LEVEL SECURITY')
    op.execute(
        'CREATE POLICY tenant_isolation_user ON "user" '
        "USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)"
    )
