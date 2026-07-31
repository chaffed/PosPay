# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import re

from tests.conftest import TenantFactory


def _login(client, tenant_slug, email, password=TenantFactory.PASSWORD):
    client.get("/ui/login")
    csrf = client.cookies.get("csrf_token")
    client.post(
        "/ui/login", data={"tenant_slug": tenant_slug, "email": email, "password": password, "csrf_token": csrf, "next": "/ui/"}
    )
    return csrf


def test_submit_paid_item_via_web(client, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="web-paid-items")
    csrf = _login(client, tenant.slug, users["admin"].email)

    new_form = client.get("/ui/paid-items/new")
    assert new_form.status_code == 200
    assert account.account_number in new_form.text

    resp = client.post(
        "/ui/paid-items",
        data={
            "account_id": str(account.id),
            "check_number": "5001",
            "presented_amount": "150.00",
            "presented_date": "2026-01-15",
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303

    list_page = client.get("/ui/paid-items")
    assert "5001" in list_page.text

    match = re.search(r"/ui/paid-items/([0-9a-f-]{36})", list_page.text)
    assert match is not None, list_page.text
    item_id = match.group(1)

    detail = client.get(f"/ui/paid-items/{item_id}")
    assert detail.status_code == 200
    assert "5001" in detail.text


def test_submit_paid_item_bad_amount_reshows_form(client, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="web-paid-items-bad-amount")
    csrf = _login(client, tenant.slug, users["admin"].email)

    resp = client.post(
        "/ui/paid-items",
        data={
            "account_id": str(account.id),
            "check_number": "5001",
            "presented_amount": "not-a-number",
            "presented_date": "2026-01-15",
            "csrf_token": csrf,
        },
    )
    assert resp.status_code == 422
    assert "Invalid amount or date" in resp.text


def test_viewer_cannot_submit_paid_item(client, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="web-paid-items-viewer-forbidden")
    _login(client, tenant.slug, users["viewer"].email)

    resp = client.get("/ui/paid-items/new", follow_redirects=False)
    assert resp.status_code == 403


def test_bulk_upload_form_requires_permission(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-bulk-paid-forbidden")
    _login(client, tenant.slug, users["viewer"].email)

    resp = client.get("/ui/paid-items/bulk", follow_redirects=False)
    assert resp.status_code == 403


def test_bulk_upload_csv_creates_paid_items_and_shows_results(client, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="web-bulk-paid-csv")
    csrf = _login(client, tenant.slug, users["admin"].email)

    content = (
        "account_number,check_number,presented_amount,presented_date\n"
        f"{account.account_number},6001,150.00,2026-01-15\n"
        f"{account.account_number},6002,not-a-number,2026-01-15\n"
        "unknown-account,6003,50.00,2026-01-15\n"
    ).encode()

    resp = client.post(
        "/ui/paid-items/bulk",
        data={"csrf_token": csrf},
        files={"upload_file": ("checks.csv", content, "text/csv")},
    )

    assert resp.status_code == 200
    assert "1 of 3 succeeded" in resp.text
    assert "No account found" in resp.text

    items_page = client.get("/ui/paid-items")
    assert "6001" in items_page.text
    assert "6002" not in items_page.text


def test_bulk_upload_with_checkbox_creates_missing_account(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-bulk-paid-auto-create")
    csrf = _login(client, tenant.slug, users["admin"].email)

    content = (
        "account_number,check_number,presented_amount,presented_date\n"
        "7001,7001,150.00,2026-01-15\n"
    ).encode()

    resp = client.post(
        "/ui/paid-items/bulk",
        data={"csrf_token": csrf, "create_missing_accounts": "true"},
        files={"upload_file": ("checks.csv", content, "text/csv")},
    )

    assert resp.status_code == 200
    assert "1 of 1 succeeded" in resp.text

    items_page = client.get("/ui/paid-items")
    assert "7001" in items_page.text


def test_bulk_upload_rejects_unparseable_file(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-bulk-paid-bad-file")
    csrf = _login(client, tenant.slug, users["admin"].email)

    resp = client.post(
        "/ui/paid-items/bulk",
        data={"csrf_token": csrf},
        files={"upload_file": ("checks.xlsx", b"not a real spreadsheet", "application/octet-stream")},
    )
    assert resp.status_code == 422
