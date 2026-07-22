import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from pospay.domain.issued_item import IssuedItem, IssuedItemSource, IssuedItemStatus
from pospay.repositories.issued_item_repo import IssuedItemRepository


@dataclass(frozen=True, slots=True)
class IssuedItemInput:
    account_id: uuid.UUID
    check_number: str
    amount: Decimal
    payee_name: str
    issue_date: date


@dataclass(frozen=True, slots=True)
class BulkRowResult:
    index: int
    success: bool
    issued_item_id: uuid.UUID | None = None
    error: str | None = None


def create_issued_item(
    session: Session,
    tenant_id: uuid.UUID,
    data: IssuedItemInput,
    *,
    submitted_by_user_id: uuid.UUID | None,
    source: IssuedItemSource = IssuedItemSource.API,
) -> IssuedItem:
    repo = IssuedItemRepository(session, tenant_id)
    item = IssuedItem(
        account_id=data.account_id,
        check_number=data.check_number,
        amount=data.amount,
        payee_name=data.payee_name,
        issue_date=data.issue_date,
        source=source,
        submitted_by_user_id=submitted_by_user_id,
    )
    repo.add(item)
    session.flush()
    return item


def create_issued_items_bulk(
    session: Session,
    tenant_id: uuid.UUID,
    items: list[IssuedItemInput],
    *,
    submitted_by_user_id: uuid.UUID | None,
) -> list[BulkRowResult]:
    results: list[BulkRowResult] = []
    for index, data in enumerate(items):
        try:
            item = create_issued_item(
                session,
                tenant_id,
                data,
                submitted_by_user_id=submitted_by_user_id,
                source=IssuedItemSource.BULK_FILE,
            )
            session.commit()
            results.append(BulkRowResult(index=index, success=True, issued_item_id=item.id))
        except Exception as exc:  # noqa: BLE001 — isolate row failures in a bulk file
            session.rollback()
            results.append(BulkRowResult(index=index, success=False, error=str(exc)))
    return results


def void_issued_item(session: Session, tenant_id: uuid.UUID, item_id: uuid.UUID, reason: str) -> IssuedItem | None:
    repo = IssuedItemRepository(session, tenant_id)
    item = repo.get(item_id)
    if item is None:
        return None
    item.status = IssuedItemStatus.VOIDED
    item.void_reason = reason
    item.voided_at = datetime.now(timezone.utc)
    session.flush()
    return item


def list_issued_items(
    session: Session, tenant_id: uuid.UUID, *, status: IssuedItemStatus | None = None, account_id: uuid.UUID | None = None
) -> list[IssuedItem]:
    repo = IssuedItemRepository(session, tenant_id)
    return repo.list(status=status, account_id=account_id)
