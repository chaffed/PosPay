# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""security groups: seed 'Bookkeeper' preset for existing tenants

Revision ID: f3a8b6e21c40
Revises: c0c354b6cab5
Create Date: 2026-08-05 09:00:00.000000

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f3a8b6e21c40'
down_revision: Union[str, None] = 'c0c354b6cab5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Must match auth/permissions.py::DEFAULT_SECURITY_GROUPS["Bookkeeper"] exactly — every
# transactional read/write plus exception recommend/decide, nothing management-related.
_BOOKKEEPER_PERMISSIONS = [
    "account:read", "account:write",
    "issued_item:read", "issued_item:write",
    "stop_payment:read", "stop_payment:write",
    "paid_item:read", "paid_item:write",
    "check_image:read", "check_image:write",
    "ach_authorization:read", "ach_authorization:write",
    "ach_transaction:read", "ach_transaction:write",
    "exception:read", "exception:recommend", "exception:decide",
]


def upgrade() -> None:
    # New named DEFAULT group (not a new permission key appended to an existing group),
    # so newly-seeded tenants pick it up automatically via
    # security_group_service.seed_default_security_groups, but every already-provisioned
    # tenant needs the row inserted here — skipping any tenant that already has a group
    # literally named "Bookkeeper" (its own pre-existing custom group, or a re-run),
    # mirroring the skip-if-already-present guard used for permission-catalog backfills.
    bind = op.get_bind()
    tenant_t = sa.table('tenant', sa.column('id', sa.Uuid()))
    security_group_t = sa.table(
        'security_group',
        sa.column('id', sa.Uuid()),
        sa.column('tenant_id', sa.Uuid()),
        sa.column('name', sa.String()),
        sa.column('permissions', sa.JSON()),
    )

    tenant_ids = [row[0] for row in bind.execute(sa.select(tenant_t.c.id)).all()]
    existing = {
        row[0]
        for row in bind.execute(
            sa.select(security_group_t.c.tenant_id).where(security_group_t.c.name == 'Bookkeeper')
        ).all()
    }
    for tenant_id in tenant_ids:
        if tenant_id in existing:
            continue
        bind.execute(
            security_group_t.insert().values(
                id=uuid.uuid4(), tenant_id=tenant_id, name='Bookkeeper', permissions=list(_BOOKKEEPER_PERMISSIONS)
            )
        )


def downgrade() -> None:
    # Only remove rows that still exactly match the seeded permission set — a tenant may
    # have edited its "Bookkeeper" group's permissions since this migration ran, and that
    # customization shouldn't be silently destroyed by a downgrade.
    bind = op.get_bind()
    security_group_t = sa.table(
        'security_group',
        sa.column('id', sa.Uuid()),
        sa.column('name', sa.String()),
        sa.column('permissions', sa.JSON()),
    )
    rows = bind.execute(
        sa.select(security_group_t.c.id, security_group_t.c.permissions).where(security_group_t.c.name == 'Bookkeeper')
    ).all()
    for group_id, permissions in rows:
        if set(permissions) != set(_BOOKKEEPER_PERMISSIONS):
            continue
        bind.execute(security_group_t.delete().where(security_group_t.c.id == group_id))
