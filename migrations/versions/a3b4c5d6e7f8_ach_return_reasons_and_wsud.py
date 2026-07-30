# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""ACH return-reason catalog + core-posting trancode, WSUD e-signature

Revision ID: a3b4c5d6e7f8
Revises: f1a2b3c4d5e6
Create Date: 2026-07-30 10:00:00.000000

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Must match services/ach_return_reason_service.py::DEFAULT_ACH_RETURN_REASONS exactly —
# back-filled here for every already-provisioned tenant (new tenants get it from
# provisioning_service.py going forward), same "seed a new default into every existing
# tenant too" precedent as f3a8b6e21c40_bookkeeper_security_group.py.
_DEFAULT_REASONS = [
    "Insufficient Funds",
    "Account Closed",
    "No Account/Unable to Locate Account",
    "Customer Advises Not Authorized",
    "Amount Not Same As Indicated",
    "Payment Stopped",
    "Uncollected Funds",
]

# Same rationale as f48f7301f98a_extend_postgres_rls_defense_in_depth_to_.py: strictly
# single-tenant tables with no cross-tenant read path, so RLS is safe to enable without
# breaking anything (unlike exception_item/decision, which the ML pipeline deliberately
# reads across all tenants).
_RLS_TABLES = ["ach_return_reason", "wsud_statement", "wsud_statement_transaction"]


def upgrade() -> None:
    op.create_table(
        'ach_return_reason',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('reason_text', sa.String(length=255), nullable=False),
        sa.Column('transaction_code', sa.String(length=10), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name=op.f('fk_ach_return_reason_tenant_id_tenant')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_ach_return_reason')),
    )
    op.create_index(op.f('ix_ach_return_reason_tenant_id'), 'ach_return_reason', ['tenant_id'], unique=False)

    op.create_table(
        'wsud_statement',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('customer_id', sa.Uuid(), nullable=False),
        sa.Column('signed_by_user_id', sa.Uuid(), nullable=False),
        sa.Column('signer_typed_name', sa.String(length=255), nullable=False),
        sa.Column('signer_ip_address', sa.String(length=64), nullable=True),
        sa.Column('signer_user_agent', sa.String(length=500), nullable=True),
        sa.Column('consent_disclosure_version', sa.String(length=20), nullable=False),
        sa.Column('statement_text_snapshot', sa.Text(), nullable=False),
        sa.Column('signed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('signature_hex', sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name=op.f('fk_wsud_statement_tenant_id_tenant')),
        sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], name=op.f('fk_wsud_statement_customer_id_customer')),
        sa.ForeignKeyConstraint(['signed_by_user_id'], ['user.id'], name=op.f('fk_wsud_statement_signed_by_user_id_user')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_wsud_statement')),
    )
    op.create_index(op.f('ix_wsud_statement_tenant_id'), 'wsud_statement', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_wsud_statement_customer_id'), 'wsud_statement', ['customer_id'], unique=False)

    op.create_table(
        'wsud_statement_transaction',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('wsud_statement_id', sa.Uuid(), nullable=False),
        sa.Column('ach_transaction_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name=op.f('fk_wsud_statement_transaction_tenant_id_tenant')),
        sa.ForeignKeyConstraint(
            ['wsud_statement_id'], ['wsud_statement.id'], name=op.f('fk_wsud_statement_transaction_wsud_statement_id_wsud_statement')
        ),
        sa.ForeignKeyConstraint(
            ['ach_transaction_id'], ['ach_transaction.id'], name=op.f('fk_wsud_statement_transaction_ach_transaction_id_ach_transaction')
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_wsud_statement_transaction')),
        sa.UniqueConstraint('wsud_statement_id', 'ach_transaction_id', name='uq_wsud_statement_transaction'),
    )
    op.create_index(op.f('ix_wsud_statement_transaction_tenant_id'), 'wsud_statement_transaction', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_wsud_statement_transaction_wsud_statement_id'), 'wsud_statement_transaction', ['wsud_statement_id'], unique=False)
    op.create_index(op.f('ix_wsud_statement_transaction_ach_transaction_id'), 'wsud_statement_transaction', ['ach_transaction_id'], unique=False)

    with op.batch_alter_table('decision') as batch_op:
        batch_op.add_column(sa.Column('return_transaction_code', sa.String(length=10), nullable=True))

    with op.batch_alter_table('exception_item') as batch_op:
        batch_op.add_column(sa.Column('recommended_return_transaction_code', sa.String(length=10), nullable=True))

    # Back-fill the starter reason set into every already-provisioned tenant — skip any
    # tenant that already has a row with that exact reason_text (its own pre-existing
    # custom reason of the same name, or a re-run), same skip-if-already-present guard as
    # the Bookkeeper security-group back-fill.
    bind = op.get_bind()
    tenant_t = sa.table('tenant', sa.column('id', sa.Uuid()))
    reason_t = sa.table(
        'ach_return_reason',
        sa.column('id', sa.Uuid()),
        sa.column('tenant_id', sa.Uuid()),
        sa.column('reason_text', sa.String()),
        sa.column('transaction_code', sa.String()),
        sa.column('is_active', sa.Boolean()),
    )

    tenant_ids = [row[0] for row in bind.execute(sa.select(tenant_t.c.id)).all()]
    for tenant_id in tenant_ids:
        existing = {
            row[0]
            for row in bind.execute(
                sa.select(reason_t.c.reason_text).where(reason_t.c.tenant_id == tenant_id)
            ).all()
        }
        for reason_text in _DEFAULT_REASONS:
            if reason_text in existing:
                continue
            bind.execute(
                reason_t.insert().values(
                    id=uuid.uuid4(), tenant_id=tenant_id, reason_text=reason_text, transaction_code=None, is_active=True
                )
            )

    if bind.dialect.name == "postgresql":
        for table in _RLS_TABLES:
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            op.execute(
                f'CREATE POLICY tenant_isolation_{table} ON "{table}" '
                f"USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)"
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in _RLS_TABLES:
            op.execute(f'DROP POLICY IF EXISTS tenant_isolation_{table} ON "{table}"')
            op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')

    with op.batch_alter_table('exception_item') as batch_op:
        batch_op.drop_column('recommended_return_transaction_code')

    with op.batch_alter_table('decision') as batch_op:
        batch_op.drop_column('return_transaction_code')

    op.drop_table('wsud_statement_transaction')
    op.drop_table('wsud_statement')
    op.drop_table('ach_return_reason')
