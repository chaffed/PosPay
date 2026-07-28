# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""customers: tenant sub-organizations with account/record segregation

Revision ID: 660947655325
Revises: 55e0637bba8d
Create Date: 2026-07-27 08:34:05.148382

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '660947655325'
down_revision: Union[str, None] = '55e0637bba8d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CUSTOMER_SCOPED_TABLES = ("account", "issued_item", "stop_payment", "paid_item", "ach_authorization_rule", "ach_transaction")


def upgrade() -> None:
    op.create_table(
        'customer',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('customer_number', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name=op.f('fk_customer_tenant_id_tenant')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_customer')),
        sa.UniqueConstraint('tenant_id', 'customer_number', name='uq_customer_tenant_number'),
    )
    op.create_index(op.f('ix_customer_tenant_id'), 'customer', ['tenant_id'], unique=False)

    # Denormalized customer_id on every table that hangs off account_id — nullable and
    # unpopulated for existing rows (NULL = unassigned/tenant-wide, i.e. zero behavior
    # change until a tenant actually starts creating customers), mirroring how tenant_id
    # is already denormalized everywhere rather than derived via joins.
    for table_name in _CUSTOMER_SCOPED_TABLES:
        op.add_column(table_name, sa.Column('customer_id', sa.Uuid(), nullable=True))
        op.create_index(op.f(f'ix_{table_name}_customer_id'), table_name, ['customer_id'], unique=False)
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_foreign_key(
                op.f(f'fk_{table_name}_customer_id_customer'), 'customer', ['customer_id'], ['id']
            )

    # tenant_membership: add customer_id (NULL = tenant-wide membership, unchanged
    # behavior for every existing row) and loosen the unique constraint from
    # (user_id, tenant_id) to (user_id, tenant_id, customer_id), since one user can now
    # hold several memberships in the same tenant — one per customer, or a tenant-wide one
    # plus per-customer overrides. Batched for SQLite, which can't ALTER a constraint
    # in place.
    with op.batch_alter_table('tenant_membership') as batch_op:
        batch_op.add_column(sa.Column('customer_id', sa.Uuid(), nullable=True))
        batch_op.drop_constraint('uq_tenant_membership_user_tenant', type_='unique')
        batch_op.create_foreign_key(
            op.f('fk_tenant_membership_customer_id_customer'), 'customer', ['customer_id'], ['id']
        )
        batch_op.create_unique_constraint(
            'uq_tenant_membership_user_tenant_customer', ['user_id', 'tenant_id', 'customer_id']
        )
    op.create_index(op.f('ix_tenant_membership_customer_id'), 'tenant_membership', ['customer_id'], unique=False)

    # New permission introduced by this migration (auth/permissions.py::PERMISSION_CATALOG)
    # — newly-seeded tenants' "Admin" group picks it up automatically since that default is
    # computed from the live catalog, but existing tenants' already-persisted "Admin" group
    # rows need it appended here, same technique as every prior permission-catalog addition.
    bind = op.get_bind()
    security_group_t = sa.table(
        'security_group',
        sa.column('id', sa.Uuid()),
        sa.column('name', sa.String()),
        sa.column('permissions', sa.JSON()),
    )
    rows = bind.execute(
        sa.select(security_group_t.c.id, security_group_t.c.permissions).where(security_group_t.c.name == 'Admin')
    ).all()
    for group_id, permissions in rows:
        if 'customer:manage' in permissions:
            continue
        bind.execute(
            security_group_t.update()
            .where(security_group_t.c.id == group_id)
            .values(permissions=[*permissions, 'customer:manage'])
        )

    if bind.dialect.name != "postgresql":
        return
    op.execute('ALTER TABLE "customer" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "customer" FORCE ROW LEVEL SECURITY')
    op.execute(
        'CREATE POLICY tenant_isolation_customer ON "customer" '
        "USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('DROP POLICY IF EXISTS tenant_isolation_customer ON "customer"')
        op.execute('ALTER TABLE "customer" NO FORCE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "customer" DISABLE ROW LEVEL SECURITY')

    op.drop_index(op.f('ix_tenant_membership_customer_id'), table_name='tenant_membership')
    with op.batch_alter_table('tenant_membership') as batch_op:
        batch_op.drop_constraint('uq_tenant_membership_user_tenant_customer', type_='unique')
        batch_op.drop_constraint(op.f('fk_tenant_membership_customer_id_customer'), type_='foreignkey')
        batch_op.create_unique_constraint('uq_tenant_membership_user_tenant', ['user_id', 'tenant_id'])
        batch_op.drop_column('customer_id')

    for table_name in _CUSTOMER_SCOPED_TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(op.f(f'fk_{table_name}_customer_id_customer'), type_='foreignkey')
        op.drop_index(op.f(f'ix_{table_name}_customer_id'), table_name=table_name)
        op.drop_column(table_name, 'customer_id')

    op.drop_index(op.f('ix_customer_tenant_id'), table_name='customer')
    op.drop_table('customer')

    # customer:manage is left in place on existing "Admin" groups on downgrade — same
    # reasoning as every prior permission-catalog downgrade in this project.
