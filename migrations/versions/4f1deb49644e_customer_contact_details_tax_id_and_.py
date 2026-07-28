"""customer contact details, tax id, and external customer id

Revision ID: 4f1deb49644e
Revises: c08922484f65
Create Date: 2026-07-27 15:23:11.804912

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4f1deb49644e'
down_revision: Union[str, None] = 'c08922484f65'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_COLUMNS = (
    ('external_customer_id', sa.String(length=64)),
    ('tax_id', sa.String(length=32)),
    ('primary_contact_name', sa.String(length=255)),
    ('email', sa.String(length=255)),
    ('phone', sa.String(length=32)),
    ('website', sa.String(length=255)),
    ('address_line1', sa.String(length=255)),
    ('address_line2', sa.String(length=255)),
    ('city', sa.String(length=100)),
    ('state', sa.String(length=50)),
    ('postal_code', sa.String(length=20)),
    ('notes', sa.String(length=1000)),
)


def upgrade() -> None:
    for name, col_type in _NEW_COLUMNS:
        op.add_column('customer', sa.Column(name, col_type, nullable=True))


def downgrade() -> None:
    for name, _col_type in reversed(_NEW_COLUMNS):
        op.drop_column('customer', name)
