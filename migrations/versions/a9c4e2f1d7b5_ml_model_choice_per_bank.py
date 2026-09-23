# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""ml: per-bank choice of shared vs bank-only model, model ownership, fraud-example
approval, platform key scopes

Revision ID: a9c4e2f1d7b5
Revises: f2a9d4c7e1b3
Create Date: 2026-09-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a9c4e2f1d7b5'
down_revision: Union[str, None] = 'f2a9d4c7e1b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Every existing bank stays on the shared model it already uses, with no 90-day
    # lock (NULL) — only banks created from now on get one.
    with op.batch_alter_table('tenant') as batch_op:
        batch_op.add_column(sa.Column(
            'ml_model_source',
            sa.Enum('SHARED', 'PRIVATE', name='ml_model_source', native_enum=False, length=10),
            nullable=False,
            server_default='SHARED',
        ))
        batch_op.add_column(sa.Column('ml_source_changed_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('ml_source_changed_by_user_id', sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column('ml_private_switch_allowed_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('ml_shared_consent_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('ml_shared_consent_by_user_id', sa.Uuid(), nullable=True))
        batch_op.create_foreign_key('fk_tenant_ml_source_changed_by_user', 'user', ['ml_source_changed_by_user_id'], ['id'])
        batch_op.create_foreign_key('fk_tenant_ml_shared_consent_by_user', 'user', ['ml_shared_consent_by_user_id'], ['id'])

    with op.batch_alter_table('ml_model') as batch_op:
        batch_op.add_column(sa.Column('tenant_id', sa.Uuid(), nullable=True))
        batch_op.create_foreign_key('fk_ml_model_tenant', 'tenant', ['tenant_id'], ['id'])
        batch_op.create_index('ix_ml_model_tenant_id', ['tenant_id'])
    # Customer models belong to their customer's bank; shared models stay NULL.
    op.execute(
        "UPDATE ml_model SET tenant_id = (SELECT customer.tenant_id FROM customer WHERE customer.id = ml_model.customer_id) "
        "WHERE customer_id IS NOT NULL"
    )

    with op.batch_alter_table('exception_item') as batch_op:
        batch_op.add_column(sa.Column('shared_training_approved_at', sa.DateTime(timezone=True), nullable=True))

    # Every key created before scopes existed was a usage-metering key.
    with op.batch_alter_table('platform_api_key') as batch_op:
        batch_op.add_column(sa.Column('scopes', sa.JSON(), nullable=False, server_default='["usage"]'))


def downgrade() -> None:
    with op.batch_alter_table('platform_api_key') as batch_op:
        batch_op.drop_column('scopes')

    with op.batch_alter_table('exception_item') as batch_op:
        batch_op.drop_column('shared_training_approved_at')

    with op.batch_alter_table('ml_model') as batch_op:
        batch_op.drop_index('ix_ml_model_tenant_id')
        batch_op.drop_constraint('fk_ml_model_tenant', type_='foreignkey')
        batch_op.drop_column('tenant_id')

    with op.batch_alter_table('tenant') as batch_op:
        batch_op.drop_constraint('fk_tenant_ml_shared_consent_by_user', type_='foreignkey')
        batch_op.drop_constraint('fk_tenant_ml_source_changed_by_user', type_='foreignkey')
        batch_op.drop_column('ml_shared_consent_by_user_id')
        batch_op.drop_column('ml_shared_consent_at')
        batch_op.drop_column('ml_private_switch_allowed_at')
        batch_op.drop_column('ml_source_changed_by_user_id')
        batch_op.drop_column('ml_source_changed_at')
        batch_op.drop_column('ml_model_source')
