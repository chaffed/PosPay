from decimal import Decimal

import pytest

from pospay.bulk_import.nacha import NachaParseError, parse_nacha_file, transaction_type_for_code


def _batch_header(*, company_name="ACME CORP", company_id="1234567890", sec_code="PPD", effective_date="260115") -> str:
    return (
        "5"
        + "200"
        + company_name.ljust(16)[:16]
        + " " * 20
        + company_id.ljust(10)[:10]
        + sec_code.ljust(3)[:3]
        + "PAYROLL   "  # company entry description, 10 chars
        + "260114"  # company descriptive date, 6 chars
        + effective_date
        + "   "  # settlement date (julian), 3 chars
        + "1"  # originator status code
        + "12345678"  # originating DFI id, 8 chars
        + "0000001"  # batch number, 7 chars
    )


def _entry_detail(
    *,
    transaction_code="22",
    dfi_account_number="000123456789",
    amount_cents="0000015000",
    individual_id="EMP001",
    trace_number="123456780000001",
) -> str:
    return (
        "6"
        + transaction_code
        + "12345678"  # receiving DFI id, 8 chars
        + "1"  # check digit
        + dfi_account_number.ljust(17)[:17]
        + amount_cents.rjust(10, "0")[:10]
        + individual_id.ljust(15)[:15]
        + "JOHN DOE".ljust(22)[:22]
        + "  "  # discretionary data
        + "0"  # addenda record indicator
        + trace_number.ljust(15)[:15]
    )


def _batch_control() -> str:
    return "8" + " " * 93


def test_parses_single_batch_single_entry():
    lines = [_batch_header(), _entry_detail(), _batch_control()]
    entries = parse_nacha_file("\n".join(lines).encode("ascii"))

    assert len(entries) == 1
    entry = entries[0]
    assert entry.company_id == "1234567890"
    assert entry.company_name == "ACME CORP"
    assert entry.sec_code == "PPD"
    assert entry.effective_date.isoformat() == "2026-01-15"
    assert entry.dfi_account_number == "000123456789"
    assert entry.amount == 150
    assert entry.individual_id == "EMP001"
    assert entry.transaction_code == "22"
    assert entry.trace_number == "123456780000001"


def test_multiple_entries_share_the_same_batch_header_context():
    lines = [
        _batch_header(company_id="9999999999"),
        _entry_detail(trace_number="000000000000001"),
        _entry_detail(trace_number="000000000000002", amount_cents="0000099999"),
        _batch_control(),
    ]
    entries = parse_nacha_file("\n".join(lines).encode("ascii"))

    assert len(entries) == 2
    assert all(e.company_id == "9999999999" for e in entries)
    assert entries[1].amount == Decimal("999.99")
    assert entries[0].trace_number == "000000000000001"
    assert entries[1].trace_number == "000000000000002"


def test_multiple_batches_with_different_originators():
    lines = [
        _batch_header(company_id="1111111111", company_name="FIRST CO"),
        _entry_detail(trace_number="000000000000001"),
        _batch_control(),
        _batch_header(company_id="2222222222", company_name="SECOND CO"),
        _entry_detail(trace_number="000000000000002"),
        _batch_control(),
    ]
    entries = parse_nacha_file("\n".join(lines).encode("ascii"))

    assert len(entries) == 2
    assert entries[0].company_id == "1111111111"
    assert entries[1].company_id == "2222222222"


def test_entry_before_any_batch_header_is_an_error():
    lines = [_entry_detail()]
    with pytest.raises(NachaParseError, match="before any batch header"):
        parse_nacha_file("\n".join(lines).encode("ascii"))


def test_missing_dfi_account_number_is_an_error():
    lines = [_batch_header(), _entry_detail(dfi_account_number=""), _batch_control()]
    with pytest.raises(NachaParseError, match="no DFI account number"):
        parse_nacha_file("\n".join(lines).encode("ascii"))


def test_empty_file_with_no_entries_is_an_error():
    with pytest.raises(NachaParseError, match="No entry detail records"):
        parse_nacha_file(b"")


def test_invalid_effective_date_is_an_error():
    lines = [_batch_header(effective_date="269999"), _entry_detail(), _batch_control()]
    with pytest.raises(NachaParseError, match="invalid effective date"):
        parse_nacha_file("\n".join(lines).encode("ascii"))


@pytest.mark.parametrize("code,expected", [("22", "credit"), ("27", "debit"), ("32", "credit"), ("37", "debit")])
def test_transaction_type_for_code(code, expected):
    assert transaction_type_for_code(code) == expected


def test_unrecognized_transaction_code_raises():
    with pytest.raises(NachaParseError, match="Unrecognized"):
        transaction_type_for_code("99")


def test_short_unpadded_lines_are_tolerated():
    # A file header/control record we don't care about, deliberately short/malformed —
    # lenient mode should still extract the entry detail correctly.
    lines = ["1 short file header", _batch_header(), _entry_detail(), _batch_control(), "9 short file control"]
    entries = parse_nacha_file("\n".join(lines).encode("ascii"))
    assert len(entries) == 1
