# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""bulk upload created record tracking table with RLS and backout columns

Revision ID: c08922484f65
Revises: 660947655325
Create Date: 2026-07-27 14:00:13.671572

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c08922484f65'
down_revision: Union[str, None] = '660947655325'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'bulk_upload_created_record',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('bulk_upload_file_id', sa.Uuid(), nullable=False),
        sa.Column('resource_type', sa.String(length=50), nullable=False),
        sa.Column('resource_id', sa.Uuid(), nullable=False),
        sa.Column('row_label', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('reversed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reversed_by_user_id', sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name=op.f('fk_bulk_upload_created_record_tenant_id_tenant')),
        sa.ForeignKeyConstraint(
            ['bulk_upload_file_id'],
            ['bulk_upload_file.id'],
            name=op.f('fk_bulk_upload_created_record_bulk_upload_file_id_bulk_upload_file'),
        ),
        sa.ForeignKeyConstraint(
            ['reversed_by_user_id'], ['user.id'], name=op.f('fk_bulk_upload_created_record_reversed_by_user_id_user')
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_bulk_upload_created_record')),
    )
    op.create_index(
        op.f('ix_bulk_upload_created_record_tenant_id'), 'bulk_upload_created_record', ['tenant_id'], unique=False
    )
    op.create_index(
        op.f('ix_bulk_upload_created_record_bulk_upload_file_id'),
        'bulk_upload_created_record',
        ['bulk_upload_file_id'],
        unique=False,
    )

    # Marks the whole upload as backed out (services/bulk_upload_reversal_service.py) --
    # nullable, unpopulated for every existing upload, zero behavior change until
    # something is actually backed out.
    op.add_column('bulk_upload_file', sa.Column('backed_out_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('bulk_upload_file', sa.Column('backed_out_by_user_id', sa.Uuid(), nullable=True))
    with op.batch_alter_table('bulk_upload_file') as batch_op:
        batch_op.create_foreign_key(
            op.f('fk_bulk_upload_file_backed_out_by_user_id_user'), 'user', ['backed_out_by_user_id'], ['id']
        )

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute('ALTER TABLE "bulk_upload_created_record" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "bulk_upload_created_record" FORCE ROW LEVEL SECURITY')
    op.execute(
        'CREATE POLICY tenant_isolation_bulk_upload_created_record ON "bulk_upload_created_record" '
        "USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('DROP POLICY IF EXISTS tenant_isolation_bulk_upload_created_record ON "bulk_upload_created_record"')
        op.execute('ALTER TABLE "bulk_upload_created_record" NO FORCE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "bulk_upload_created_record" DISABLE ROW LEVEL SECURITY')

    with op.batch_alter_table('bulk_upload_file') as batch_op:
        batch_op.drop_constraint(op.f('fk_bulk_upload_file_backed_out_by_user_id_user'), type_='foreignkey')
        batch_op.drop_column('backed_out_by_user_id')
        batch_op.drop_column('backed_out_at')

    op.drop_index(op.f('ix_bulk_upload_created_record_bulk_upload_file_id'), table_name='bulk_upload_created_record')
    op.drop_index(op.f('ix_bulk_upload_created_record_tenant_id'), table_name='bulk_upload_created_record')
    op.drop_table('bulk_upload_created_record')
