# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import re

from tests.conftest import TenantFactory


def _login(client, tenant_slug, email, password=TenantFactory.PASSWORD):
    client.get("/ui/login")
    csrf = client.cookies.get("csrf_token")
    return client.post(
        "/ui/login", data={"tenant_slug": tenant_slug, "email": email, "password": password, "csrf_token": csrf, "next": "/ui/"}
    )


def test_create_account_and_issued_item_via_web(client, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="web-issued-items")
    _login(client, tenant.slug, users["admin"].email)

    accounts_page = client.get("/ui/accounts")
    assert accounts_page.status_code == 200
    assert account.account_number in accounts_page.text

    csrf = client.cookies.get("csrf_token")
    created = client.post(
        "/ui/accounts", data={"account_number": "999", "name": "Payroll", "csrf_token": csrf}, follow_redirects=False
    )
    assert created.status_code == 303

    new_form = client.get("/ui/issued-items/new")
    assert new_form.status_code == 200
    assert "Payroll" in new_form.text

    resp = client.post(
        "/ui/issued-items",
        data={
            "account_id": str(account.id),
            "check_number": "5001",
            "amount": "150.00",
            "payee_name": "Vendor X",
            "issue_date": "2026-01-01",
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303

    list_page = client.get("/ui/issued-items")
    assert "5001" in list_page.text

    match = re.search(r"/ui/issued-items/([0-9a-f-]{36})", list_page.text)
    assert match is not None, list_page.text
    item_id = match.group(1)

    detail = client.get(f"/ui/issued-items/{item_id}")
    assert detail.status_code == 200
    assert "outstanding" in detail.text

    void_resp = client.post(f"/ui/issued-items/{item_id}/void", data={"reason": "test", "csrf_token": csrf}, follow_redirects=False)
    assert void_resp.status_code == 303

    detail_after = client.get(f"/ui/issued-items/{item_id}")
    assert "voided" in detail_after.text


def test_viewer_cannot_create_issued_item(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-viewer-forbidden")
    _login(client, tenant.slug, users["viewer"].email)

    resp = client.get("/ui/issued-items/new", follow_redirects=False)
    assert resp.status_code == 403


def test_issued_item_detail_404_for_unknown_id(client, tenant_factory):
    import uuid

    tenant, _account, users = tenant_factory.make(slug="web-issued-item-404")
    _login(client, tenant.slug, users["admin"].email)

    resp = client.get(f"/ui/issued-items/{uuid.uuid4()}")
    assert resp.status_code == 404
