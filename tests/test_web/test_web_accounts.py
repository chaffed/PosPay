# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from pospay.services import account_service
from tests.conftest import TenantFactory


def _login(client, tenant_slug, email, password=TenantFactory.PASSWORD):
    client.get("/ui/login")
    csrf = client.cookies.get("csrf_token")
    return client.post(
        "/ui/login", data={"tenant_slug": tenant_slug, "email": email, "password": password, "csrf_token": csrf, "next": "/ui/"}
    )


def _csrf(client):
    return client.cookies.get("csrf_token")


def test_new_account_form_renders(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-acct-new-form")
    _login(client, tenant.slug, users["admin"].email)

    resp = client.get("/ui/accounts/new")
    assert resp.status_code == 200
    assert 'name="account_number"' in resp.text
    assert 'action="/ui/accounts"' in resp.text


def test_accounts_list_links_to_new_account_page(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-acct-list-links-new")
    _login(client, tenant.slug, users["admin"].email)

    resp = client.get("/ui/accounts")
    assert resp.status_code == 200
    assert 'href="/ui/accounts/new"' in resp.text


def test_create_account_with_external_id_via_web_form(client, db_session, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-acct-external")
    _login(client, tenant.slug, users["admin"].email)
    client.get("/ui/accounts/new")

    resp = client.post(
        "/ui/accounts",
        data={"account_number": "9001", "name": "Payroll", "external_account_id": "CUST-REF-5", "csrf_token": _csrf(client)},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    db_session.expire_all()
    account = account_service.get_account_by_number(db_session, tenant.id, "CUST-REF-5")
    assert account is not None
    assert account.account_number == "9001"


def test_accounts_list_page_shows_external_id_column(client, db_session, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-acct-list")
    account_service.create_account(
        db_session, tenant.id, account_service.AccountInput(account_number="9002", name="Reserve", external_account_id="CUST-REF-6")
    )
    db_session.commit()
    _login(client, tenant.slug, users["admin"].email)

    resp = client.get("/ui/accounts")

    assert resp.status_code == 200
    assert "CUST-REF-6" in resp.text


def test_bulk_upload_accounts_sets_external_id(client, db_session, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="web-acct-bulk")
    _login(client, tenant.slug, users["admin"].email)
    client.get("/ui/accounts/bulk")

    csv_content = b"account_number,name,external_account_id\n9003,Escrow,CUST-REF-7\n"
    resp = client.post(
        "/ui/accounts/bulk",
        data={"csrf_token": _csrf(client)},
        files={"upload_file": ("accounts.csv", csv_content, "text/csv")},
    )

    assert resp.status_code == 200
    assert "1 of 1 succeeded" in resp.text
    db_session.expire_all()
    account = account_service.get_account_by_number(db_session, tenant.id, "CUST-REF-7")
    assert account is not None
    assert account.account_number == "9003"
