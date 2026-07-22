import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from pospay.bulk_import.fields import RowFieldError, parse_date, parse_decimal, require_str
from pospay.bulk_import.results import BulkFileRowResult
from pospay.domain.issued_item import IssuedItem, IssuedItemSource, IssuedItemStatus
from pospay.repositories.issued_item_repo import IssuedItemRepository
from pospay.services import account_service


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


def _issued_item_input_from_row(session: Session, tenant_id: uuid.UUID, row: dict[str, Any]) -> IssuedItemInput:
    """Raises RowFieldError on any missing/invalid field or unrecognized account_number
    — callers (create_issued_items_from_rows) catch this per-row so one bad row doesn't
    fail the whole file. Expected (case/whitespace-insensitive) columns: account_number,
    check_number, amount, payee_name, issue_date."""
    account_number = require_str(row, "account_number")
    account = account_service.get_account_by_number(session, tenant_id, account_number)
    if account is None:
        raise RowFieldError(f"No account found with account number {account_number!r}")

    return IssuedItemInput(
        account_id=account.id,
        check_number=require_str(row, "check_number"),
        amount=parse_decimal(row, "amount"),
        payee_name=require_str(row, "payee_name"),
        issue_date=parse_date(row, "issue_date"),
    )


def create_issued_items_from_rows(
    session: Session,
    tenant_id: uuid.UUID,
    rows: list[dict[str, Any]],
    *,
    submitted_by_user_id: uuid.UUID | None,
) -> list[BulkFileRowResult]:
    """Entry point for delimited/Excel bulk uploads (see web/routers/issued_items.py) —
    each row carries its own account_number (resolved to this tenant's account), unlike
    the JSON API's /issued-items/bulk which takes a single tenant-wide account per item
    already as a UUID. One DB transaction per row, same isolation pattern as
    create_issued_items_bulk, so a single bad row doesn't roll back the whole file."""
    results: list[BulkFileRowResult] = []
    for index, row in enumerate(rows):
        row_label = f"row {index + 2}"  # +2: 1-based, plus the header row itself
        try:
            data = _issued_item_input_from_row(session, tenant_id, row)
            item = create_issued_item(
                session, tenant_id, data, submitted_by_user_id=submitted_by_user_id, source=IssuedItemSource.BULK_FILE
            )
            session.commit()
            results.append(BulkFileRowResult(row_label=row_label, success=True, created_id=item.id))
        except RowFieldError as exc:
            session.rollback()
            results.append(BulkFileRowResult(row_label=row_label, success=False, error=str(exc)))
        except Exception as exc:  # noqa: BLE001 — isolate row failures (e.g. duplicate check number) in a bulk file
            session.rollback()
            results.append(BulkFileRowResult(row_label=row_label, success=False, error=str(exc)))
    return results
