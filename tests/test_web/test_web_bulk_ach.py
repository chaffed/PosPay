# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from tests.conftest import TenantFactory


def _login(client, tenant_slug, email, password=TenantFactory.PASSWORD):
    client.get("/ui/login")
    csrf = client.cookies.get("csrf_token")
    client.post(
        "/ui/login", data={"tenant_slug": tenant_slug, "email": email, "password": password, "csrf_token": csrf, "next": "/ui/"}
    )
    return csrf


def _nacha_batch_header(company_id="1234567890", company_name="ACME CORP", sec_code="PPD", effective_date="260115") -> str:
    return (
        "5" + "200" + company_name.ljust(16)[:16] + " " * 20 + company_id.ljust(10)[:10] + sec_code.ljust(3)[:3]
        + "PAYROLL   " + "260114" + effective_date + "   " + "1" + "12345678" + "0000001"
    )


def _nacha_entry_detail(dfi_account_number, amount_cents="0000015000", transaction_code="22", trace_number="123456780000001") -> str:
    return (
        "6" + transaction_code + "12345678" + "1" + dfi_account_number.ljust(17)[:17]
        + amount_cents.rjust(10, "0")[:10] + "EMP001".ljust(15)[:15] + "JOHN DOE".ljust(22)[:22]
        + "  " + "0" + trace_number.ljust(15)[:15]
    )


def test_bulk_upload_form_requires_permission(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-bulk-ach-forbidden")
    _login(client, tenant.slug, users["viewer"].email)

    resp = client.get("/ui/ach/transactions/bulk", follow_redirects=False)
    assert resp.status_code == 403


def test_bulk_upload_csv_creates_transactions(client, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="web-bulk-ach-csv")
    csrf = _login(client, tenant.slug, users["admin"].email)

    content = (
        "account_number,originator_id,originator_name,receiver_id,amount,transaction_type,sec_code,trace_number,effective_date\n"
        f"{account.account_number},ORIG1,Payroll Co,,10.00,credit,PPD,T1,2026-01-10\n"
        f"unknown-account,ORIG2,Other Co,,20.00,debit,WEB,T2,2026-01-10\n"
    ).encode()

    resp = client.post(
        "/ui/ach/transactions/bulk",
        data={"csrf_token": csrf, "format": "tabular"},
        files={"upload_file": ("txns.csv", content, "text/csv")},
    )

    assert resp.status_code == 200
    assert "1 of 2 succeeded" in resp.text
    assert "No account found" in resp.text

    txns_page = client.get("/ui/ach/transactions")
    assert "Payroll Co" in txns_page.text


def test_bulk_upload_nacha_file_creates_transactions(client, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="web-bulk-ach-nacha")
    csrf = _login(client, tenant.slug, users["admin"].email)

    lines = [
        _nacha_batch_header(company_id="1234567890", company_name="ACME CORP"),
        _nacha_entry_detail(dfi_account_number=account.account_number, trace_number="123456780000001"),
        "8" + " " * 93,
    ]
    content = "\n".join(lines).encode("ascii")

    resp = client.post(
        "/ui/ach/transactions/bulk",
        data={"csrf_token": csrf, "format": "nacha"},
        files={"upload_file": ("payroll.ach", content, "application/octet-stream")},
    )

    assert resp.status_code == 200
    assert "1 of 1 succeeded" in resp.text

    txns_page = client.get("/ui/ach/transactions")
    assert "ACME CORP" in txns_page.text


def test_bulk_upload_nacha_rejects_malformed_file(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-bulk-ach-nacha-bad")
    csrf = _login(client, tenant.slug, users["admin"].email)

    resp = client.post(
        "/ui/ach/transactions/bulk",
        data={"csrf_token": csrf, "format": "nacha"},
        files={"upload_file": ("empty.ach", b"", "application/octet-stream")},
    )
    assert resp.status_code == 422
    assert "No entry detail records" in resp.text


def test_bulk_upload_csv_with_checkbox_creates_missing_account(client, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="web-bulk-ach-csv-auto-create")
    csrf = _login(client, tenant.slug, users["admin"].email)

    content = (
        "account_number,originator_id,originator_name,receiver_id,amount,transaction_type,sec_code,trace_number,effective_date\n"
        f"{account.account_number},ORIG1,Payroll Co,,10.00,credit,PPD,T1,2026-01-10\n"
        "9401,ORIG2,Other Co,,20.00,credit,WEB,T2,2026-01-10\n"
    ).encode()

    resp = client.post(
        "/ui/ach/transactions/bulk",
        data={"csrf_token": csrf, "format": "tabular", "create_missing_accounts": "true"},
        files={"upload_file": ("txns.csv", content, "text/csv")},
    )

    assert resp.status_code == 200
    assert "2 of 2 succeeded" in resp.text


def test_bulk_upload_nacha_with_checkbox_creates_missing_account(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-bulk-ach-nacha-auto-create")
    csrf = _login(client, tenant.slug, users["admin"].email)

    lines = [
        _nacha_batch_header(),
        _nacha_entry_detail(dfi_account_number="9402"),
        "8" + " " * 93,
    ]
    content = "\n".join(lines).encode("ascii")

    resp = client.post(
        "/ui/ach/transactions/bulk",
        data={"csrf_token": csrf, "format": "nacha", "create_missing_accounts": "true"},
        files={"upload_file": ("payroll.ach", content, "application/octet-stream")},
    )

    assert resp.status_code == 200
    assert "1 of 1 succeeded" in resp.text


def test_bulk_upload_nacha_with_unmatched_account_reported(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-bulk-ach-nacha-unmatched")
    csrf = _login(client, tenant.slug, users["admin"].email)

    lines = [
        _nacha_batch_header(),
        _nacha_entry_detail(dfi_account_number="0000000000"),
        "8" + " " * 93,
    ]
    content = "\n".join(lines).encode("ascii")

    resp = client.post(
        "/ui/ach/transactions/bulk",
        data={"csrf_token": csrf, "format": "nacha"},
        files={"upload_file": ("payroll.ach", content, "application/octet-stream")},
    )
    assert resp.status_code == 200
    assert "0 of 1 succeeded" in resp.text
    assert "No account found" in resp.text
