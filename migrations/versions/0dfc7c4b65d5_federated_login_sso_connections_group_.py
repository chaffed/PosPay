# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""federated login: sso connections, group mappings, password-login enforcement flags

Revision ID: 0dfc7c4b65d5
Revises: f6430779fb01
Create Date: 2026-07-29 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0dfc7c4b65d5'
down_revision: Union[str, None] = 'f6430779fb01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RLS_TABLES = ("sso_connection", "sso_group_mapping")


def upgrade() -> None:
    op.create_table(
        'sso_connection',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('customer_id', sa.Uuid(), nullable=True),
        sa.Column('provider', sa.Enum('OKTA', 'AZURE_AD', name='sso_provider', native_enum=False, length=20), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=False),
        sa.Column('issuer', sa.String(length=500), nullable=False),
        sa.Column('client_id', sa.String(length=255), nullable=False),
        sa.Column('client_secret_encrypted', sa.String(length=1000), nullable=False),
        sa.Column('groups_claim_name', sa.String(length=100), nullable=False, server_default='groups'),
        sa.Column('auto_provision', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name=op.f('fk_sso_connection_tenant_id_tenant')),
        sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], name=op.f('fk_sso_connection_customer_id_customer')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_sso_connection')),
    )
    op.create_index(op.f('ix_sso_connection_tenant_id'), 'sso_connection', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_sso_connection_customer_id'), 'sso_connection', ['customer_id'], unique=False)

    op.create_table(
        'sso_group_mapping',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('connection_id', sa.Uuid(), nullable=False),
        sa.Column('external_group', sa.String(length=255), nullable=False),
        sa.Column('security_group_id', sa.Uuid(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name=op.f('fk_sso_group_mapping_tenant_id_tenant')),
        sa.ForeignKeyConstraint(
            ['connection_id'], ['sso_connection.id'], name=op.f('fk_sso_group_mapping_connection_id_sso_connection')
        ),
        sa.ForeignKeyConstraint(
            ['security_group_id'], ['security_group.id'], name=op.f('fk_sso_group_mapping_security_group_id_security_group')
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_sso_group_mapping')),
    )
    op.create_index(op.f('ix_sso_group_mapping_tenant_id'), 'sso_group_mapping', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_sso_group_mapping_connection_id'), 'sso_group_mapping', ['connection_id'], unique=False)

    # NULL is impossible here (nullable=False, default=True) — zero behavior change for
    # every existing row: password login stays exactly as it works today until an admin
    # explicitly turns it off, which services/sso_service.py refuses to allow unless at
    # least one active, group-mapped SSO connection already exists for that scope.
    op.add_column('tenant', sa.Column('password_login_enabled', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('customer', sa.Column('password_login_enabled', sa.Boolean(), nullable=False, server_default=sa.true()))

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in _RLS_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY tenant_isolation_{table} ON "{table}" '
            "USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in _RLS_TABLES:
            op.execute(f'DROP POLICY IF EXISTS tenant_isolation_{table} ON "{table}"')
            op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')

    op.drop_column('customer', 'password_login_enabled')
    op.drop_column('tenant', 'password_login_enabled')

    op.drop_index(op.f('ix_sso_group_mapping_connection_id'), table_name='sso_group_mapping')
    op.drop_index(op.f('ix_sso_group_mapping_tenant_id'), table_name='sso_group_mapping')
    op.drop_table('sso_group_mapping')

    op.drop_index(op.f('ix_sso_connection_customer_id'), table_name='sso_connection')
    op.drop_index(op.f('ix_sso_connection_tenant_id'), table_name='sso_connection')
    op.drop_table('sso_connection')
