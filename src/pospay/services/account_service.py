# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from pospay.bulk_import.fields import RowFieldError, optional_str, require_str
from pospay.bulk_import.results import BulkFileRowResult
from pospay.domain.account import Account, AchDebitBlockMode
from pospay.repositories.account_repo import AccountRepository
from pospay.services import customer_service


@dataclass(frozen=True, slots=True)
class AccountInput:
    account_number: str
    name: str
    # None = unassigned "house" account, visible only to tenant-wide staff — see
    # domain/tenant_membership.py::customer_id and CustomerScopedRepository.
    customer_id: uuid.UUID | None = None
    ach_debit_block_mode: AchDebitBlockMode | None = None


def create_account(session: Session, tenant_id: uuid.UUID, data: AccountInput) -> Account:
    repo = AccountRepository(session, tenant_id)
    account = Account(account_number=data.account_number, name=data.name, customer_id=data.customer_id)
    if data.ach_debit_block_mode is not None:
        account.ach_debit_block_mode = data.ach_debit_block_mode
    repo.add(account)
    session.flush()
    return account


def list_accounts(session: Session, tenant_id: uuid.UUID, *, customer_id: uuid.UUID | None = None) -> list[Account]:
    return AccountRepository(session, tenant_id, customer_id).list()


def get_account_by_number(
    session: Session, tenant_id: uuid.UUID, account_number: str, *, customer_id: uuid.UUID | None = None
) -> Account | None:
    """Used by bulk file imports (issued items, ACH) to resolve a human-readable account
    number in an uploaded row/entry to this tenant's internal account id — files never
    carry our UUIDs, only the account number a user would actually recognize.
    `customer_id` scopes the lookup exactly like any other CustomerScopedRepository read —
    a customer-scoped bulk upload can only match its own customer's accounts."""
    matches = AccountRepository(session, tenant_id, customer_id).list(account_number=account_number)
    return matches[0] if matches else None


def get_or_create_account_by_number(
    session: Session,
    tenant_id: uuid.UUID,
    account_number: str,
    *,
    default_name: str | None = None,
    customer_id: uuid.UUID | None = None,
) -> Account:
    """Used by bulk file imports when the "create missing accounts" option is checked —
    same lookup as get_account_by_number, but creates a new account instead of returning
    None when the file references an account number this tenant doesn't have yet. Files
    rarely carry an account name, so callers may pass one (e.g. from an optional
    "account_name" column) and it otherwise falls back to a placeholder derived from the
    number itself. A newly-created account inherits `customer_id` from the caller's own
    scope, so a customer-scoped upload can never auto-create an unassigned or
    other-customer account."""
    account = get_account_by_number(session, tenant_id, account_number, customer_id=customer_id)
    if account is not None:
        return account
    return create_account(
        session,
        tenant_id,
        AccountInput(
            account_number=account_number,
            name=default_name or f"Account {account_number}",
            customer_id=customer_id,
        ),
    )


def set_ach_debit_block_mode(session: Session, tenant_id: uuid.UUID, account_id: uuid.UUID, mode: AchDebitBlockMode) -> Account | None:
    repo = AccountRepository(session, tenant_id)
    account = repo.get(account_id)
    if account is None:
        return None
    account.ach_debit_block_mode = mode
    session.flush()
    return account


def _account_input_from_row(
    session: Session, tenant_id: uuid.UUID, row: dict[str, Any], *, scoped_customer_id: uuid.UUID | None
) -> AccountInput:
    """Raises RowFieldError on any missing/invalid field. Expected (case/whitespace-
    insensitive) columns: account_number, name, customer_number (optional — blank means
    an unassigned "house" account), ach_debit_block_mode (optional).

    When the upload itself is customer-scoped (scoped_customer_id is not None — see
    web/routers/accounts.py), every row is stamped with that customer regardless of
    whether a customer_number column is present; if one IS present it must name that same
    customer, since a customer-scoped upload can never create another customer's (or an
    unassigned) account."""
    account_number = require_str(row, "account_number")
    name = require_str(row, "name")
    customer_number = optional_str(row, "customer_number")

    if scoped_customer_id is not None:
        if customer_number:
            customer = customer_service.get_customer_by_number(session, tenant_id, customer_number)
            if customer is None or customer.id != scoped_customer_id:
                raise RowFieldError(f"customer_number {customer_number!r} does not match your assigned customer")
        customer_id = scoped_customer_id
    elif customer_number:
        customer = customer_service.get_customer_by_number(session, tenant_id, customer_number)
        if customer is None:
            raise RowFieldError(f"No customer found with customer number {customer_number!r}")
        customer_id = customer.id
    else:
        customer_id = None

    mode_raw = optional_str(row, "ach_debit_block_mode")
    ach_debit_block_mode = None
    if mode_raw:
        try:
            ach_debit_block_mode = AchDebitBlockMode(mode_raw.strip().lower())
        except ValueError:
            valid = ", ".join(m.value for m in AchDebitBlockMode)
            raise RowFieldError(f"'ach_debit_block_mode' must be one of {valid}, got {mode_raw!r}") from None

    return AccountInput(
        account_number=account_number, name=name, customer_id=customer_id, ach_debit_block_mode=ach_debit_block_mode
    )


def create_accounts_from_rows(
    session: Session,
    tenant_id: uuid.UUID,
    rows: list[dict[str, Any]],
    *,
    scoped_customer_id: uuid.UUID | None = None,
) -> list[BulkFileRowResult]:
    """Entry point for the accounts bulk upload (web/routers/accounts.py) — same
    per-row-transaction isolation pattern as every other bulk import in this app, so one
    bad row doesn't roll back the whole file."""
    results: list[BulkFileRowResult] = []
    for index, row in enumerate(rows):
        row_label = f"row {index + 2}"  # +2: 1-based, plus the header row itself
        try:
            data = _account_input_from_row(session, tenant_id, row, scoped_customer_id=scoped_customer_id)
            account = create_account(session, tenant_id, data)
            session.commit()
            results.append(BulkFileRowResult(row_label=row_label, success=True, created_id=account.id))
        except RowFieldError as exc:
            session.rollback()
            results.append(BulkFileRowResult(row_label=row_label, success=False, error=str(exc)))
        except Exception as exc:  # noqa: BLE001 — isolate row failures (e.g. duplicate account number) in a bulk file
            session.rollback()
            results.append(BulkFileRowResult(row_label=row_label, success=False, error=str(exc)))
    return results
