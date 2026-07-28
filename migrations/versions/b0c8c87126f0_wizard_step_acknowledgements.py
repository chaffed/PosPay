# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""implementation wizard: manual step acknowledgements

Revision ID: b0c8c87126f0
Revises: 99a184bb2c97
Create Date: 2026-07-31 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b0c8c87126f0'
down_revision: Union[str, None] = '99a184bb2c97'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'wizard_step_ack',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('customer_id', sa.Uuid(), nullable=True),
        sa.Column('step_key', sa.String(length=100), nullable=False),
        sa.Column('acknowledged_by_user_id', sa.Uuid(), nullable=False),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name=op.f('fk_wizard_step_ack_tenant_id_tenant')),
        sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], name=op.f('fk_wizard_step_ack_customer_id_customer')),
        sa.ForeignKeyConstraint(
            ['acknowledged_by_user_id'], ['user.id'], name=op.f('fk_wizard_step_ack_acknowledged_by_user_id_user')
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_wizard_step_ack')),
        sa.UniqueConstraint('tenant_id', 'customer_id', 'step_key', name='uq_wizard_step_ack_scope_step'),
    )
    op.create_index(op.f('ix_wizard_step_ack_tenant_id'), 'wizard_step_ack', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_wizard_step_ack_customer_id'), 'wizard_step_ack', ['customer_id'], unique=False)

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute('ALTER TABLE "wizard_step_ack" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "wizard_step_ack" FORCE ROW LEVEL SECURITY')
    op.execute(
        'CREATE POLICY tenant_isolation_wizard_step_ack ON "wizard_step_ack" '
        "USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('DROP POLICY IF EXISTS tenant_isolation_wizard_step_ack ON "wizard_step_ack"')
        op.execute('ALTER TABLE "wizard_step_ack" NO FORCE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "wizard_step_ack" DISABLE ROW LEVEL SECURITY')

    op.drop_index(op.f('ix_wizard_step_ack_customer_id'), table_name='wizard_step_ack')
    op.drop_index(op.f('ix_wizard_step_ack_tenant_id'), table_name='wizard_step_ack')
    op.drop_table('wizard_step_ack')
