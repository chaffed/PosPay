from tests.conftest import login_headers


def test_void_issued_item(client, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="void-test")
    headers = login_headers(client, tenant.slug, users["preparer"].email)

    created = client.post(
        "/api/v1/issued-items",
        headers=headers,
        json={
            "account_id": str(account.id),
            "check_number": "8001",
            "amount": "150.00",
            "payee_name": "Theta Inc",
            "issue_date": "2026-01-01",
        },
    ).json()

    voided = client.patch(
        f"/api/v1/issued-items/{created['id']}/void", headers=headers, json={"reason": "Issued in error"}
    )
    assert voided.status_code == 200
    assert voided.json()["status"] == "voided"
    assert voided.json()["void_reason"] == "Issued in error"


def test_cancel_stop_payment(client, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="cancel-stop-test")
    headers = login_headers(client, tenant.slug, users["preparer"].email)

    stop = client.post(
        "/api/v1/stop-payments",
        headers=headers,
        json={"account_id": str(account.id), "check_number": "8002", "effective_date": "2026-01-01"},
    ).json()

    cancelled = client.patch(f"/api/v1/stop-payments/{stop['id']}/cancel", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    active = client.get("/api/v1/stop-payments/outstanding", headers=headers).json()
    assert cancelled.json()["id"] not in [s["id"] for s in active]


def test_viewer_role_cannot_write_issued_items(client, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="viewer-forbidden")
    headers = login_headers(client, tenant.slug, users["viewer"].email)

    resp = client.post(
        "/api/v1/issued-items",
        headers=headers,
        json={
            "account_id": str(account.id),
            "check_number": "8003",
            "amount": "100.00",
            "payee_name": "Iota LLC",
            "issue_date": "2026-01-01",
        },
    )
    assert resp.status_code == 403
