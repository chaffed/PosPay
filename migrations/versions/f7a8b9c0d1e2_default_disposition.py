# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""default disposition: customer_disposition_setting table, decision.source + nullable decided_by_user_id

Revision ID: f7a8b9c0d1e2
Revises: e5f6a7b8c9d0
Create Date: 2026-08-06 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'customer_disposition_setting',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('customer_id', sa.Uuid(), nullable=False),
        sa.Column('network_code', sa.String(length=32), nullable=False),
        sa.Column(
            'mode',
            sa.Enum('NONE', 'FIXED_PAY', 'FIXED_RETURN', 'ML_DETERMINED', name='disposition_mode', native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column('response_window_hours', sa.Integer(), nullable=True),
        sa.Column('default_ach_return_reason_id', sa.Uuid(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name=op.f('fk_customer_disposition_setting_tenant_id_tenant')),
        sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], name=op.f('fk_customer_disposition_setting_customer_id_customer')),
        sa.ForeignKeyConstraint(
            ['network_code'], ['payment_network.code'], name=op.f('fk_customer_disposition_setting_network_code_payment_network')
        ),
        sa.ForeignKeyConstraint(
            ['default_ach_return_reason_id'], ['ach_return_reason.id'],
            name=op.f('fk_customer_disposition_setting_default_ach_return_reason_id_ach_return_reason'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_customer_disposition_setting')),
        sa.UniqueConstraint('customer_id', 'network_code', name='uq_customer_disposition_setting_customer_network'),
    )
    op.create_index(
        op.f('ix_customer_disposition_setting_tenant_id'), 'customer_disposition_setting', ['tenant_id'], unique=False
    )
    op.create_index(
        op.f('ix_customer_disposition_setting_customer_id'), 'customer_disposition_setting', ['customer_id'], unique=False
    )

    with op.batch_alter_table('decision') as batch_op:
        batch_op.alter_column('decided_by_user_id', existing_type=sa.Uuid(), nullable=True)
        batch_op.add_column(
            sa.Column(
                'source',
                sa.Enum('HUMAN', 'AUTO_DEFAULT', 'AUTO_ML', name='decision_source', native_enum=False, length=15),
                nullable=False,
                server_default='human',
            )
        )

    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute('ALTER TABLE "customer_disposition_setting" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "customer_disposition_setting" FORCE ROW LEVEL SECURITY')
    op.execute(
        'CREATE POLICY tenant_isolation_customer_disposition_setting ON "customer_disposition_setting" '
        "USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('DROP POLICY IF EXISTS tenant_isolation_customer_disposition_setting ON "customer_disposition_setting"')
        op.execute('ALTER TABLE "customer_disposition_setting" NO FORCE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "customer_disposition_setting" DISABLE ROW LEVEL SECURITY')

    with op.batch_alter_table('decision') as batch_op:
        batch_op.drop_column('source')
        batch_op.alter_column('decided_by_user_id', existing_type=sa.Uuid(), nullable=False)

    op.drop_index(op.f('ix_customer_disposition_setting_customer_id'), table_name='customer_disposition_setting')
    op.drop_index(op.f('ix_customer_disposition_setting_tenant_id'), table_name='customer_disposition_setting')
    op.drop_table('customer_disposition_setting')
