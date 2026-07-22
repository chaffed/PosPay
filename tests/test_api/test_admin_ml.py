from datetime import date
from decimal import Decimal

from pospay.db.tenancy import TenantContext
from pospay.domain.decision import DecisionOutcome
from pospay.networks.check.ingestion import PaidItemSubmission, ingest_paid_item
from pospay.services import decision_service, issued_item_service
from tests.conftest import login_headers


def _seed_labeled_decisions(db_session, tenant, account, users, count: int = 12) -> None:
    for i in range(count):
        issued_item_service.create_issued_item(
            db_session,
            tenant.id,
            issued_item_service.IssuedItemInput(
                account_id=account.id,
                check_number=f"70{i:02d}",
                amount=Decimal("100.00"),
                payee_name="Vendor",
                issue_date=date(2026, 1, 1),
            ),
            submitted_by_user_id=users["preparer"].id,
        )
        db_session.commit()
        paid_item = ingest_paid_item(
            db_session,
            tenant.id,
            PaidItemSubmission(
                account_id=account.id,
                check_number=f"70{i:02d}",
                presented_amount=Decimal("999.00" if i % 2 == 0 else "888.00"),
                presented_date=date(2026, 1, 10),
            ),
        )
        db_session.commit()

        from pospay.repositories.exception_repo import ExceptionRepository

        exception = ExceptionRepository(db_session, tenant.id).list(source_item_id=paid_item.id)[0]
        ctx = TenantContext(tenant_id=tenant.id, user_id=users["approver"].id, role="approver")
        outcome = DecisionOutcome.RETURN if i % 2 == 0 else DecisionOutcome.PAY
        decision_service.decide(db_session, tenant.id, exception.id, ctx, outcome=outcome, reason_code="test", notes=None)
        db_session.commit()


def test_retrain_endpoint_trains_and_promotes_model(client, db_session, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="admin-ml-retrain")
    _seed_labeled_decisions(db_session, tenant, account, users)

    headers = login_headers(client, tenant.slug, users["admin"].email)
    resp = client.post("/api/v1/admin/ml/retrain", headers=headers, params={"network_code": "check"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["network_code"] == "check"
    assert body["promoted"] is True
    assert body["model"]["status"] == "active"


def test_retrain_endpoint_rejects_insufficient_data(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="admin-ml-insufficient")
    headers = login_headers(client, tenant.slug, users["admin"].email)

    resp = client.post("/api/v1/admin/ml/retrain", headers=headers, params={"network_code": "check"})

    assert resp.status_code == 409


def test_list_and_activate_ml_models(client, db_session, tenant_factory):
    tenant, account, users = tenant_factory.make(slug="admin-ml-list")
    _seed_labeled_decisions(db_session, tenant, account, users)
    headers = login_headers(client, tenant.slug, users["admin"].email)

    client.post("/api/v1/admin/ml/retrain", headers=headers, params={"network_code": "check"})

    models = client.get("/api/v1/admin/ml/models", headers=headers, params={"network_code": "check"}).json()
    assert len(models) >= 1
    model_id = models[0]["id"]

    activated = client.patch(f"/api/v1/admin/ml/models/{model_id}/activate", headers=headers)
    assert activated.status_code == 200
    assert activated.json()["status"] == "active"


def test_non_admin_cannot_trigger_retrain(client, tenant_factory):
    tenant, _account, users = tenant_factory.make(slug="admin-ml-forbidden")
    headers = login_headers(client, tenant.slug, users["preparer"].email)

    resp = client.post("/api/v1/admin/ml/retrain", headers=headers, params={"network_code": "check"})

    assert resp.status_code == 403
