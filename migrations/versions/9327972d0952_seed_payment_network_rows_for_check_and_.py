# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""seed payment_network rows for check and ach

Revision ID: 9327972d0952
Revises: 18baeeaca329
Create Date: 2026-07-18 16:45:03.213252

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9327972d0952'
down_revision: Union[str, None] = '18baeeaca329'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


payment_network = sa.table(
    "payment_network",
    sa.column("code", sa.String),
    sa.column("name", sa.String),
    sa.column("settlement_timing", sa.String),
    sa.column("is_active", sa.Boolean),
)


def upgrade() -> None:
    # settlement_timing must be the enum member's NAME ("ASYNC_REVIEWABLE"), not its value
    # ("async_reviewable") -- SQLAlchemy's default Enum(SettlementTiming, ...) column type
    # (domain/payment_network.py) serializes/deserializes by member name with no
    # values_callable configured anywhere in this app, so a lowercase value here would
    # insert fine but raise LookupError the moment anything reads it back through the ORM.
    op.bulk_insert(
        payment_network,
        [
            {"code": "check", "name": "Check", "settlement_timing": "ASYNC_REVIEWABLE", "is_active": True},
            {"code": "ach", "name": "ACH", "settlement_timing": "ASYNC_REVIEWABLE", "is_active": True},
        ],
    )


def downgrade() -> None:
    op.execute(payment_network.delete().where(payment_network.c.code.in_(["check", "ach"])))
