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


def test_bulk_upload_form_requires_permission(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-bulk-issued-forbidden")
    _login(client, tenant.slug, users["viewer"].email)

    resp = client.get("/ui/issued-items/bulk", follow_redirects=False)
    assert resp.status_code == 403


def test_bulk_upload_csv_creates_items_and_shows_results(client, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="web-bulk-issued-csv")
    csrf = _login(client, tenant.slug, users["admin"].email)

    content = (
        f"account_number,check_number,amount,payee_name,issue_date\n"
        f"{account.account_number},9001,150.00,Vendor A,2026-01-01\n"
        f"{account.account_number},9002,not-a-number,Vendor B,2026-01-02\n"
        f"unknown-account,9003,50.00,Vendor C,2026-01-03\n"
    ).encode()

    resp = client.post(
        "/ui/issued-items/bulk",
        data={"csrf_token": csrf},
        files={"upload_file": ("items.csv", content, "text/csv")},
    )

    assert resp.status_code == 200
    assert "1 of 3 succeeded" in resp.text
    assert "amount" in resp.text  # error message for row 2 mentions the field
    assert "No account found" in resp.text  # error message for row 3

    items_page = client.get("/ui/issued-items")
    assert "9001" in items_page.text
    assert "9002" not in items_page.text


def test_bulk_upload_xlsx_creates_items(client, tenant_factory):
    import io

    from openpyxl import Workbook

    tenant, account, users = tenant_factory.make(slug="web-bulk-issued-xlsx")
    csrf = _login(client, tenant.slug, users["admin"].email)

    wb = Workbook()
    ws = wb.active
    ws.append(["account_number", "check_number", "amount", "payee_name", "issue_date"])
    ws.append([account.account_number, "9101", 200.0, "Vendor X", "2026-01-05"])
    buffer = io.BytesIO()
    wb.save(buffer)

    resp = client.post(
        "/ui/issued-items/bulk",
        data={"csrf_token": csrf},
        files={"upload_file": ("items.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert resp.status_code == 200
    assert "1 of 1 succeeded" in resp.text

    items_page = client.get("/ui/issued-items")
    assert "9101" in items_page.text


def test_bulk_upload_with_checkbox_creates_missing_account(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-bulk-issued-auto-create")
    csrf = _login(client, tenant.slug, users["admin"].email)

    content = (
        "account_number,check_number,amount,payee_name,issue_date\n"
        "9201,9201,150.00,Vendor A,2026-01-01\n"
    ).encode()

    resp = client.post(
        "/ui/issued-items/bulk",
        data={"csrf_token": csrf, "create_missing_accounts": "true"},
        files={"upload_file": ("items.csv", content, "text/csv")},
    )

    assert resp.status_code == 200
    assert "1 of 1 succeeded" in resp.text

    items_page = client.get("/ui/issued-items")
    assert "9201" in items_page.text


def test_bulk_upload_without_checkbox_still_reports_missing_account(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-bulk-issued-no-auto-create")
    csrf = _login(client, tenant.slug, users["admin"].email)

    content = (
        "account_number,check_number,amount,payee_name,issue_date\n"
        "9301,9301,150.00,Vendor A,2026-01-01\n"
    ).encode()

    resp = client.post(
        "/ui/issued-items/bulk",
        data={"csrf_token": csrf},
        files={"upload_file": ("items.csv", content, "text/csv")},
    )

    assert resp.status_code == 200
    assert "0 of 1 succeeded" in resp.text
    assert "No account found" in resp.text


def test_bulk_upload_rejects_unparseable_file(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-bulk-issued-bad-file")
    csrf = _login(client, tenant.slug, users["admin"].email)

    resp = client.post(
        "/ui/issued-items/bulk",
        data={"csrf_token": csrf},
        files={"upload_file": ("items.xlsx", b"not a real spreadsheet", "application/octet-stream")},
    )
    assert resp.status_code == 422
