# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import uuid
from typing import Any

from sqlalchemy.orm import Session

from pospay.domain.exception_item import ExceptionItem, ExceptionStatus
from pospay.repositories.exception_repo import ExceptionRepository


def list_exceptions(
    session: Session,
    tenant_id: uuid.UUID,
    *,
    network_code: str | None = None,
    status: ExceptionStatus | None = None,
    customer_id: uuid.UUID | None = None,
    limit: int | None = None,
    offset: int | None = None,
    order_by: Any = None,
) -> list[ExceptionItem]:
    repo = ExceptionRepository(session, tenant_id, customer_id)
    return repo.list(network_code=network_code, status=status, limit=limit, offset=offset, order_by=order_by)


def get_exception(
    session: Session, tenant_id: uuid.UUID, exception_id: uuid.UUID, *, customer_id: uuid.UUID | None = None
) -> ExceptionItem | None:
    repo = ExceptionRepository(session, tenant_id, customer_id)
    return repo.get(exception_id)
