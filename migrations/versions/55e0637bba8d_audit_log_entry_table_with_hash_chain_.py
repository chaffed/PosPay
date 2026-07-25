"""audit log entry table with hash chain, audit_log read permission backfill

Revision ID: 55e0637bba8d
Revises: bc099ed56cb6
Create Date: 2026-07-24 20:59:03.661746

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '55e0637bba8d'
down_revision: Union[str, None] = 'bc099ed56cb6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_log_entry',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('actor_user_id', sa.Uuid(), nullable=True),
        sa.Column('channel', sa.Enum('WEB', 'API', name='audit_channel', native_enum=False, length=10), nullable=False),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('summary', sa.String(length=500), nullable=False),
        sa.Column('resource_type', sa.String(length=50), nullable=False),
        sa.Column('resource_id', sa.Uuid(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('prev_entry_hash', sa.String(length=64), nullable=True),
        sa.Column('entry_hash', sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(['actor_user_id'], ['user.id'], name=op.f('fk_audit_log_entry_actor_user_id_user')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name=op.f('fk_audit_log_entry_tenant_id_tenant')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_log_entry')),
    )
    op.create_index(op.f('ix_audit_log_entry_tenant_id'), 'audit_log_entry', ['tenant_id'], unique=False)

    # New permission introduced by this migration (auth/permissions.py::PERMISSION_CATALOG)
    # — newly-seeded tenants' "Admin" group picks it up automatically since that default is
    # computed from the live catalog, but existing tenants' already-persisted "Admin" group
    # rows need it appended here, same technique as the tenant:manage backfill (1eaf946c25b8).
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
        if 'audit_log:read' in permissions:
            continue
        bind.execute(
            security_group_t.update()
            .where(security_group_t.c.id == group_id)
            .values(permissions=[*permissions, 'audit_log:read'])
        )

    if bind.dialect.name != "postgresql":
        return
    op.execute('ALTER TABLE "audit_log_entry" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "audit_log_entry" FORCE ROW LEVEL SECURITY')
    op.execute(
        'CREATE POLICY tenant_isolation_audit_log_entry ON "audit_log_entry" '
        "USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('DROP POLICY IF EXISTS tenant_isolation_audit_log_entry ON "audit_log_entry"')
        op.execute('ALTER TABLE "audit_log_entry" NO FORCE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "audit_log_entry" DISABLE ROW LEVEL SECURITY')

    op.drop_index(op.f('ix_audit_log_entry_tenant_id'), table_name='audit_log_entry')
    op.drop_table('audit_log_entry')

    # audit_log:read is left in place on existing "Admin" groups on downgrade — same
    # reasoning as tenant:manage's downgrade (1eaf946c25b8): stripping a permission an
    # admin may have since granted to a custom group isn't a schema concern.
