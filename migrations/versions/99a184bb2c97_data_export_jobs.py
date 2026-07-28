# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""data portability: data export job tracking table

Revision ID: 99a184bb2c97
Revises: 0dfc7c4b65d5
Create Date: 2026-07-30 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '99a184bb2c97'
down_revision: Union[str, None] = '0dfc7c4b65d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'data_export_job',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('customer_id', sa.Uuid(), nullable=True),
        sa.Column('requested_by_user_id', sa.Uuid(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', name='data_export_job_status', native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column('archive_path', sa.String(length=1000), nullable=True),
        sa.Column('size_bytes', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.String(length=1000), nullable=True),
        sa.Column('requested_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name=op.f('fk_data_export_job_tenant_id_tenant')),
        sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], name=op.f('fk_data_export_job_customer_id_customer')),
        sa.ForeignKeyConstraint(
            ['requested_by_user_id'], ['user.id'], name=op.f('fk_data_export_job_requested_by_user_id_user')
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_data_export_job')),
    )
    op.create_index(op.f('ix_data_export_job_tenant_id'), 'data_export_job', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_data_export_job_customer_id'), 'data_export_job', ['customer_id'], unique=False)

    # NOTE: no PERMISSION_CATALOG backfill step here for existing tenants' "Admin"
    # groups, unlike every prior permission-catalog-addition migration in this project.
    # That's deliberate: data_export:run is intentionally NOT part of the default Admin
    # grant (see auth/permissions.py::_NOT_ADMIN_DEFAULT) — a bank must explicitly add it
    # to a security group via /ui/security-groups, for both new and existing tenants.

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute('ALTER TABLE "data_export_job" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "data_export_job" FORCE ROW LEVEL SECURITY')
    op.execute(
        'CREATE POLICY tenant_isolation_data_export_job ON "data_export_job" '
        "USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('DROP POLICY IF EXISTS tenant_isolation_data_export_job ON "data_export_job"')
        op.execute('ALTER TABLE "data_export_job" NO FORCE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "data_export_job" DISABLE ROW LEVEL SECURITY')

    op.drop_index(op.f('ix_data_export_job_customer_id'), table_name='data_export_job')
    op.drop_index(op.f('ix_data_export_job_tenant_id'), table_name='data_export_job')
    op.drop_table('data_export_job')
