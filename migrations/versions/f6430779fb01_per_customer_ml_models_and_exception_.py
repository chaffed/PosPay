# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""per-customer ML models and exception/decision customer scoping

Revision ID: f6430779fb01
Revises: 4f1deb49644e
Create Date: 2026-07-28 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6430779fb01'
down_revision: Union[str, None] = '4f1deb49644e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ml_model.customer_id: NULL (unchanged for every existing row) = the original
    # global, network-wide model; a value scopes that row to one customer's own model —
    # see ml/train.py, ml/predict.py.
    op.add_column('ml_model', sa.Column('customer_id', sa.Uuid(), nullable=True))
    op.create_index(op.f('ix_ml_model_customer_id'), 'ml_model', ['customer_id'], unique=False)
    with op.batch_alter_table('ml_model') as batch_op:
        batch_op.create_foreign_key(op.f('fk_ml_model_customer_id_customer'), 'customer', ['customer_id'], ['id'])

    # exception_item.customer_id: denormalized from the source item's own customer_id at
    # creation time, same pattern as issued_item/paid_item/ach_transaction's own
    # customer_id columns — both what per-customer ML groups training/scoring on, and
    # what closes exception_item/decision's customer-scoping gap (ExceptionRepository is
    # now a CustomerScopedRepository, see repositories/exception_repo.py).
    op.add_column('exception_item', sa.Column('customer_id', sa.Uuid(), nullable=True))
    op.create_index(op.f('ix_exception_item_customer_id'), 'exception_item', ['customer_id'], unique=False)
    with op.batch_alter_table('exception_item') as batch_op:
        batch_op.create_foreign_key(
            op.f('fk_exception_item_customer_id_customer'), 'customer', ['customer_id'], ['id']
        )

    op.create_table(
        'customer_ml_setting',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('customer_id', sa.Uuid(), nullable=False),
        sa.Column('network_code', sa.String(length=32), nullable=False),
        sa.Column(
            'mode',
            sa.Enum('AUTO', 'GLOBAL', 'CUSTOMER', name='ml_scoring_mode', native_enum=False, length=10),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name=op.f('fk_customer_ml_setting_tenant_id_tenant')),
        sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], name=op.f('fk_customer_ml_setting_customer_id_customer')),
        sa.ForeignKeyConstraint(
            ['network_code'], ['payment_network.code'], name=op.f('fk_customer_ml_setting_network_code_payment_network')
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_customer_ml_setting')),
        sa.UniqueConstraint('customer_id', 'network_code', name='uq_customer_ml_setting_customer_network'),
    )
    op.create_index(op.f('ix_customer_ml_setting_tenant_id'), 'customer_ml_setting', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_customer_ml_setting_customer_id'), 'customer_ml_setting', ['customer_id'], unique=False)

    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute('ALTER TABLE "customer_ml_setting" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "customer_ml_setting" FORCE ROW LEVEL SECURITY')
    op.execute(
        'CREATE POLICY tenant_isolation_customer_ml_setting ON "customer_ml_setting" '
        "USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('DROP POLICY IF EXISTS tenant_isolation_customer_ml_setting ON "customer_ml_setting"')
        op.execute('ALTER TABLE "customer_ml_setting" NO FORCE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "customer_ml_setting" DISABLE ROW LEVEL SECURITY')

    op.drop_index(op.f('ix_customer_ml_setting_customer_id'), table_name='customer_ml_setting')
    op.drop_index(op.f('ix_customer_ml_setting_tenant_id'), table_name='customer_ml_setting')
    op.drop_table('customer_ml_setting')

    with op.batch_alter_table('exception_item') as batch_op:
        batch_op.drop_constraint(op.f('fk_exception_item_customer_id_customer'), type_='foreignkey')
    op.drop_index(op.f('ix_exception_item_customer_id'), table_name='exception_item')
    op.drop_column('exception_item', 'customer_id')

    with op.batch_alter_table('ml_model') as batch_op:
        batch_op.drop_constraint(op.f('fk_ml_model_customer_id_customer'), type_='foreignkey')
    op.drop_index(op.f('ix_ml_model_customer_id'), table_name='ml_model')
    op.drop_column('ml_model', 'customer_id')
