# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""ml_model: record each artifact file's SHA-256 so it's verified before unpickling

Revision ID: c3e8f1a5d9b2
Revises: b7d3e9a2c4f1
Create Date: 2026-09-23 20:00:00.000000

"""
import hashlib
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3e8f1a5d9b2'
down_revision: Union[str, None] = 'b7d3e9a2c4f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _sha256_of(path: str) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def upgrade() -> None:
    with op.batch_alter_table('ml_model') as batch_op:
        batch_op.add_column(sa.Column('artifact_sha256', sa.String(length=64), nullable=True))

    # Pin the files that exist today (migrations run where the app runs, so artifact paths
    # resolve the same way). A row whose file can't be read stays NULL, and ml/registry.py
    # refuses to load it: that model gives no scores until it's retrained or replaced.
    bind = op.get_bind()
    ml_model = sa.table('ml_model', sa.column('id', sa.Uuid()), sa.column('artifact_path', sa.String()), sa.column('artifact_sha256', sa.String()))
    rows = bind.execute(sa.select(ml_model.c.id, ml_model.c.artifact_path)).all()
    for row_id, artifact_path in rows:
        digest = _sha256_of(artifact_path) if artifact_path else None
        if digest is not None:
            bind.execute(sa.update(ml_model).where(ml_model.c.id == row_id).values(artifact_sha256=digest))


def downgrade() -> None:
    with op.batch_alter_table('ml_model') as batch_op:
        batch_op.drop_column('artifact_sha256')
