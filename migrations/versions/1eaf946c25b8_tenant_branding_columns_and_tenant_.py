"""tenant branding columns and tenant:manage permission backfill

Revision ID: 1eaf946c25b8
Revises: ba635450e77c
Create Date: 2026-07-24 19:24:59.537704

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '1eaf946c25b8'
down_revision: Union[str, None] = 'ba635450e77c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tenant', sa.Column('logo_path', sa.String(length=1000), nullable=True))
    op.add_column('tenant', sa.Column('logo_content_type', sa.String(length=100), nullable=True))
    op.add_column('tenant', sa.Column('favicon_path', sa.String(length=1000), nullable=True))
    op.add_column('tenant', sa.Column('favicon_content_type', sa.String(length=100), nullable=True))
    op.add_column('tenant', sa.Column('accent_color', sa.String(length=7), nullable=True))

    # New permission introduced by this migration (auth/permissions.py::PERMISSION_CATALOG)
    # — newly-seeded tenants' "Admin" group picks it up automatically since that default is
    # computed from the live catalog, but existing tenants' already-persisted "Admin" group
    # rows need it appended here, the same Python-side JSON-list-append backfill technique
    # used by the security-groups migration (23275a18351d).
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
        if 'tenant:manage' in permissions:
            continue
        bind.execute(
            security_group_t.update()
            .where(security_group_t.c.id == group_id)
            .values(permissions=[*permissions, 'tenant:manage'])
        )


def downgrade() -> None:
    op.drop_column('tenant', 'accent_color')
    op.drop_column('tenant', 'favicon_content_type')
    op.drop_column('tenant', 'favicon_path')
    op.drop_column('tenant', 'logo_content_type')
    op.drop_column('tenant', 'logo_path')

    # tenant:manage is left in place on downgrade — removing a permission from existing
    # groups isn't a schema concern and risks stripping something an admin already relied
    # on if they upgraded, granted it to a custom group, then downgraded.
