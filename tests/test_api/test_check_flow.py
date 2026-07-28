# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from tests.conftest import login_headers


def test_full_flow_clean_match(client, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="flow-match")
    headers = login_headers(client, tenant.slug, users["preparer"].email)

    issued = client.post(
        "/api/v1/issued-items",
        headers=headers,
        json={
            "account_id": str(account.id),
            "check_number": "1001",
            "amount": "250.00",
            "payee_name": "Acme Supply Co",
            "issue_date": "2026-01-01",
        },
    )
    assert issued.status_code == 201, issued.text
    assert issued.json()["status"] == "outstanding"

    paid = client.post(
        "/api/v1/paid-items",
        headers=headers,
        json={
            "account_id": str(account.id),
            "check_number": "1001",
            "presented_amount": "250.00",
            "presented_date": "2026-01-10",
        },
    )
    assert paid.status_code == 201, paid.text
    assert paid.json()["match_status"] == "matched"
    assert paid.json()["settlement_status"] == "paid"

    outstanding = client.get("/api/v1/issued-items/outstanding", headers=headers)
    assert issued.json()["id"] not in [i["id"] for i in outstanding.json()]

    exceptions = client.get("/api/v1/exceptions", headers=headers)
    assert exceptions.json() == []


def test_full_flow_exception_then_single_approval_decision(client, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="flow-exception", require_dual_control=False)
    headers = login_headers(client, tenant.slug, users["preparer"].email)

    client.post(
        "/api/v1/issued-items",
        headers=headers,
        json={
            "account_id": str(account.id),
            "check_number": "2001",
            "amount": "500.00",
            "payee_name": "Beta Vendor LLC",
            "issue_date": "2026-01-01",
        },
    )

    paid = client.post(
        "/api/v1/paid-items",
        headers=headers,
        json={
            "account_id": str(account.id),
            "check_number": "2001",
            "presented_amount": "999.00",
            "presented_date": "2026-01-10",
        },
    )
    assert paid.json()["match_status"] == "exception"

    exceptions = client.get("/api/v1/exceptions", headers=headers).json()
    assert len(exceptions) == 1
    assert "amount_mismatch" in exceptions[0]["exception_types"]
    exception_id = exceptions[0]["id"]

    approver_headers = login_headers(client, tenant.slug, users["approver"].email)
    decide = client.post(
        f"/api/v1/exceptions/{exception_id}/decide",
        headers=approver_headers,
        json={"outcome": "return", "reason_code": "confirmed_fraud", "notes": "Amount does not match issued check"},
    )
    assert decide.status_code == 200, decide.text
    assert decide.json()["outcome"] == "return"

    fetched = client.get(f"/api/v1/exceptions/{exception_id}", headers=headers).json()
    assert fetched["status"] == "return"


def test_dual_control_requires_recommendation_before_decide(client, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="dual-control", require_dual_control=True)
    preparer_headers = login_headers(client, tenant.slug, users["preparer"].email)
    approver_headers = login_headers(client, tenant.slug, users["approver"].email)

    client.post(
        "/api/v1/issued-items",
        headers=preparer_headers,
        json={
            "account_id": str(account.id),
            "check_number": "3001",
            "amount": "500.00",
            "payee_name": "Gamma Inc",
            "issue_date": "2026-01-01",
        },
    )
    client.post(
        "/api/v1/paid-items",
        headers=preparer_headers,
        json={
            "account_id": str(account.id),
            "check_number": "3001",
            "presented_amount": "600.00",
            "presented_date": "2026-01-10",
        },
    )
    exception_id = client.get("/api/v1/exceptions", headers=preparer_headers).json()[0]["id"]

    # Deciding without a prior recommendation must be rejected under dual control.
    premature = client.post(
        f"/api/v1/exceptions/{exception_id}/decide",
        headers=approver_headers,
        json={"outcome": "pay", "reason_code": "authorized_exception"},
    )
    assert premature.status_code == 409

    recommend = client.post(
        f"/api/v1/exceptions/{exception_id}/recommend",
        headers=preparer_headers,
        json={"outcome": "pay", "reason_code": "authorized_exception"},
    )
    assert recommend.status_code == 200
    assert recommend.json()["status"] == "pending_approval"

    decide = client.post(
        f"/api/v1/exceptions/{exception_id}/decide",
        headers=approver_headers,
        json={"outcome": "pay", "reason_code": "authorized_exception"},
    )
    assert decide.status_code == 200
    assert decide.json()["outcome"] == "pay"


def test_maker_cannot_approve_own_recommendation(client, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="maker-checker-conflict", require_dual_control=True)
    admin_headers = login_headers(client, tenant.slug, users["admin"].email)

    client.post(
        "/api/v1/issued-items",
        headers=admin_headers,
        json={
            "account_id": str(account.id),
            "check_number": "4001",
            "amount": "500.00",
            "payee_name": "Delta Co",
            "issue_date": "2026-01-01",
        },
    )
    client.post(
        "/api/v1/paid-items",
        headers=admin_headers,
        json={
            "account_id": str(account.id),
            "check_number": "4001",
            "presented_amount": "700.00",
            "presented_date": "2026-01-10",
        },
    )
    exception_id = client.get("/api/v1/exceptions", headers=admin_headers).json()[0]["id"]

    # admin has both preparer and approver permissions, so the same user recommends and
    # then tries to approve their own recommendation — must be rejected.
    client.post(
        f"/api/v1/exceptions/{exception_id}/recommend",
        headers=admin_headers,
        json={"outcome": "pay", "reason_code": "authorized_exception"},
    )
    conflict = client.post(
        f"/api/v1/exceptions/{exception_id}/decide",
        headers=admin_headers,
        json={"outcome": "pay", "reason_code": "authorized_exception"},
    )
    assert conflict.status_code == 403


def test_stop_payment_blocks_matching_paid_item(client, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="stop-blocks")
    headers = login_headers(client, tenant.slug, users["preparer"].email)

    client.post(
        "/api/v1/issued-items",
        headers=headers,
        json={
            "account_id": str(account.id),
            "check_number": "5001",
            "amount": "500.00",
            "payee_name": "Epsilon Corp",
            "issue_date": "2026-01-01",
        },
    )
    client.post(
        "/api/v1/stop-payments",
        headers=headers,
        json={
            "account_id": str(account.id),
            "check_number": "5001",
            "effective_date": "2026-01-05",
            "reason": "Lost check",
        },
    )

    paid = client.post(
        "/api/v1/paid-items",
        headers=headers,
        json={
            "account_id": str(account.id),
            "check_number": "5001",
            "presented_amount": "500.00",
            "presented_date": "2026-01-10",
        },
    )
    assert paid.json()["match_status"] == "exception"

    exceptions = client.get("/api/v1/exceptions", headers=headers).json()
    assert exceptions[0]["exception_types"] == ["stopped"]


def test_bulk_issued_items_partial_failure_isolates_bad_rows(client, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="bulk-partial")
    headers = login_headers(client, tenant.slug, users["preparer"].email)

    # Second row has a duplicate check_number with the first — unique constraint violation.
    resp = client.post(
        "/api/v1/issued-items/bulk",
        headers=headers,
        json=[
            {
                "account_id": str(account.id),
                "check_number": "6001",
                "amount": "100.00",
                "payee_name": "Zeta LLC",
                "issue_date": "2026-01-01",
            },
            {
                "account_id": str(account.id),
                "check_number": "6001",
                "amount": "200.00",
                "payee_name": "Zeta LLC",
                "issue_date": "2026-01-02",
            },
            {
                "account_id": str(account.id),
                "check_number": "6002",
                "amount": "300.00",
                "payee_name": "Eta LLC",
                "issue_date": "2026-01-03",
            },
        ],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["succeeded"] == 2
    assert body["failed"] == 1
    assert body["results"][1]["success"] is False


def test_exceptions_and_paid_items_are_tenant_isolated(client, tenant_factory):
    tenant_a, account_a, users_a = tenant_factory.make(slug="isolation-a")
    tenant_b, account_b, users_b = tenant_factory.make(slug="isolation-b")
    headers_a = login_headers(client, tenant_a.slug, users_a["preparer"].email)
    headers_b = login_headers(client, tenant_b.slug, users_b["preparer"].email)

    client.post(
        "/api/v1/paid-items",
        headers=headers_a,
        json={
            "account_id": str(account_a.id),
            "check_number": "7001",
            "presented_amount": "100.00",
            "presented_date": "2026-01-10",
        },
    )

    # Tenant B must see zero exceptions even though tenant A just created one.
    exceptions_b = client.get("/api/v1/exceptions", headers=headers_b).json()
    assert exceptions_b == []

    exceptions_a = client.get("/api/v1/exceptions", headers=headers_a).json()
    assert len(exceptions_a) == 1
