# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""Lenient NACHA (ACH file format) parser.

Extracts only what's needed to create ach_transaction rows: batch header fields
(company id/name, SEC code, effective date) and entry detail fields (DFI account
number, amount, individual id, transaction code, trace number). Does NOT validate file
header (record type 1), addenda (type 7), batch control (type 8), or file control (type
9) records — no entry-count/dollar-total/entry-hash cross-checking against what the
file's control records claim. A genuinely malformed file can still partially "parse"
here rather than being rejected outright; see the architecture notes on why this was a
deliberate v1 scope decision (full control-total validation is meaningfully more code
and a real risk of rejecting legitimate-but-slightly-off files).

Field positions below are 1-indexed per the NACHA spec, standard 94-character records.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation


class NachaParseError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class NachaEntry:
    line_number: int
    dfi_account_number: str
    amount: Decimal
    individual_id: str | None  # -> ach receiver_id
    transaction_code: str
    trace_number: str
    company_id: str  # -> ach originator_id, from the enclosing batch header
    company_name: str  # -> ach originator_name
    sec_code: str
    effective_date: date


# Transaction Code (entry detail, positions 2-3) -> debit/credit. Checking (2x) and
# savings (3x) accounts each have credit/prenote-credit/zero-dollar-credit and the debit
# equivalents; prenotes and zero-dollar entries still move real money in our model, so
# they're mapped the same as their non-prenote counterpart rather than treated specially.
_CREDIT_CODES = {"22", "23", "24", "32", "33", "34"}
_DEBIT_CODES = {"27", "28", "29", "37", "38", "39"}


def transaction_type_for_code(transaction_code: str) -> str:
    if transaction_code in _CREDIT_CODES:
        return "credit"
    if transaction_code in _DEBIT_CODES:
        return "debit"
    raise NachaParseError(f"Unrecognized or unsupported transaction code {transaction_code!r}")


def parse_nacha_file(content: bytes) -> list[NachaEntry]:
    try:
        text = content.decode("ascii")
    except UnicodeDecodeError:
        text = content.decode("ascii", errors="replace")

    entries: list[NachaEntry] = []
    current_batch: dict | None = None

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.rstrip("\n\r")
        if not line.strip():
            continue
        if len(line) < 94:
            line = line.ljust(94)  # tolerate short/unpadded trailing records

        record_type = line[0]

        if record_type == "5":  # Batch Header
            current_batch = {
                "company_name": line[4:20].strip(),
                "company_id": line[40:50].strip(),
                "sec_code": line[50:53].strip(),
                "effective_date": _parse_yymmdd(line[69:75].strip(), line_number),
            }

        elif record_type == "6":  # Entry Detail
            if current_batch is None:
                raise NachaParseError(f"Line {line_number}: entry detail record appears before any batch header")

            transaction_code = line[1:3]
            dfi_account_number = line[12:29].strip()
            amount_cents = line[29:39].strip()
            individual_id = line[39:54].strip() or None
            trace_number = line[79:94].strip()

            if not dfi_account_number:
                raise NachaParseError(f"Line {line_number}: entry detail record has no DFI account number")
            try:
                amount = Decimal(amount_cents) / Decimal(100)
            except InvalidOperation:
                raise NachaParseError(f"Line {line_number}: invalid amount field {amount_cents!r}") from None

            entries.append(
                NachaEntry(
                    line_number=line_number,
                    dfi_account_number=dfi_account_number,
                    amount=amount,
                    individual_id=individual_id,
                    transaction_code=transaction_code,
                    trace_number=trace_number,
                    company_id=current_batch["company_id"],
                    company_name=current_batch["company_name"],
                    sec_code=current_batch["sec_code"],
                    effective_date=current_batch["effective_date"],
                )
            )

        elif record_type == "8":  # Batch Control
            current_batch = None  # closes the batch; an entry detail after this without a new '5' is an error

        # Record types 1 (file header), 7 (addenda), 9 (file control) are intentionally
        # ignored in lenient mode.

    if not entries:
        raise NachaParseError("No entry detail records (type '6') found in this file")

    return entries


def _parse_yymmdd(raw: str, line_number: int) -> date:
    if len(raw) != 6 or not raw.isdigit():
        raise NachaParseError(f"Line {line_number}: invalid effective date field {raw!r}")
    yy, mm, dd = int(raw[0:2]), int(raw[2:4]), int(raw[4:6])
    year = 2000 + yy if yy < 80 else 1900 + yy  # standard NACHA 2-digit-year pivot
    try:
        return date(year, mm, dd)
    except ValueError:
        raise NachaParseError(f"Line {line_number}: invalid effective date {raw!r}") from None
