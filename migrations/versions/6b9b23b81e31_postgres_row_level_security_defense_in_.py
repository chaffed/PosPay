"""postgres row-level security defense-in-depth on single-tenant tables

Revision ID: 6b9b23b81e31
Revises: 20876d626ec0
Create Date: 2026-07-18 17:51:21.069071

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '6b9b23b81e31'
down_revision: Union[str, None] = '20876d626ec0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Defense-in-depth only — primary tenant isolation is the repository-layer filter in
# repositories/base.py, which is what every cross-tenant-isolation test in
# tests/test_api/test_cross_tenant_isolation.py actually exercises. RLS is a second,
# independent layer for Postgres production deployments; SQLite/MSSQL rely on the
# repository filter alone (RLS syntax isn't portable to either).
#
# Deliberately EXCLUDES exception_item and decision: the ML retraining pipeline
# (ml/train.py, workers/tasks.py) reads decisions and exceptions ACROSS ALL TENANTS by
# design — that's the "global model, tenant_id as a feature" decision documented in the
# architecture plan, chosen specifically to avoid a cold-start problem for new tenants.
# A blanket RLS policy on these two tables would silently break that read path the
# moment this runs against real Postgres. If you need RLS on these tables too, the
# correct fix is a separate bypass-RLS Postgres role for the ML service's own connection
# (`GRANT BYPASSRLS` or `SET ROLE`), not exempting a session variable per query.
_TENANT_SCOPED_TABLES = [
    "account",
    "user",
    "issued_item",
    "stop_payment",
    "check_image",
    "paid_item",
    "ach_authorization_rule",
    "ach_transaction",
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table in _TENANT_SCOPED_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        # FORCE is required or the table owner (typically the app's own migration/connection
        # role) bypasses RLS entirely, silently defeating the policy for normal app traffic.
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY tenant_isolation_{table} ON "{table}" '
            f"USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table in _TENANT_SCOPED_TABLES:
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation_{table} ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
