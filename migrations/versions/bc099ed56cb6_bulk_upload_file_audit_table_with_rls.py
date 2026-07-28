# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""bulk upload file audit table with RLS

Revision ID: bc099ed56cb6
Revises: 1eaf946c25b8
Create Date: 2026-07-24 20:28:18.009700

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'bc099ed56cb6'
down_revision: Union[str, None] = '1eaf946c25b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'bulk_upload_file',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column(
            'kind',
            sa.Enum('ISSUED_ITEMS', 'ACH_TRANSACTIONS', 'USERS', name='bulk_upload_kind', native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column('original_filename', sa.String(length=500), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=True),
        sa.Column('storage_path', sa.String(length=1000), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('sha256_hex', sa.String(length=64), nullable=False),
        sa.Column('hmac_signature_hex', sa.String(length=64), nullable=False),
        sa.Column('succeeded_count', sa.Integer(), nullable=True),
        sa.Column('failed_count', sa.Integer(), nullable=True),
        sa.Column('uploaded_by_user_id', sa.Uuid(), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name=op.f('fk_bulk_upload_file_tenant_id_tenant')),
        sa.ForeignKeyConstraint(
            ['uploaded_by_user_id'], ['user.id'], name=op.f('fk_bulk_upload_file_uploaded_by_user_id_user')
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_bulk_upload_file')),
    )
    op.create_index(op.f('ix_bulk_upload_file_tenant_id'), 'bulk_upload_file', ['tenant_id'], unique=False)

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute('ALTER TABLE "bulk_upload_file" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "bulk_upload_file" FORCE ROW LEVEL SECURITY')
    op.execute(
        'CREATE POLICY tenant_isolation_bulk_upload_file ON "bulk_upload_file" '
        "USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('DROP POLICY IF EXISTS tenant_isolation_bulk_upload_file ON "bulk_upload_file"')
        op.execute('ALTER TABLE "bulk_upload_file" NO FORCE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "bulk_upload_file" DISABLE ROW LEVEL SECURITY')

    op.drop_index(op.f('ix_bulk_upload_file_tenant_id'), table_name='bulk_upload_file')
    op.drop_table('bulk_upload_file')
