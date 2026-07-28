import uuid
from datetime import date
from decimal import Decimal

import pytest

from pospay.db.tenancy import TenantContext
from pospay.domain.decision import DecisionOutcome
from pospay.networks.check.ingestion import PaidItemSubmission, ingest_paid_item
from pospay.services import decision_service, issued_item_service


def _make_exception(db_session, tenant, account, users, check_number: str, issued_amount: str, presented_amount: str):
    issued_item_service.create_issued_item(
        db_session,
        tenant.id,
        issued_item_service.IssuedItemInput(
            account_id=account.id,
            check_number=check_number,
            amount=Decimal(issued_amount),
            payee_name="Some Vendor",
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
            check_number=check_number,
            presented_amount=Decimal(presented_amount),
            presented_date=date(2026, 1, 10),
        ),
    )
    db_session.commit()

    from pospay.repositories.exception_repo import ExceptionRepository

    exceptions = ExceptionRepository(db_session, tenant.id).list(source_item_id=paid_item.id)
    return exceptions[0]


def _decide(db_session, tenant, users, exception, outcome: DecisionOutcome):
    # decision_service.decide only reads ctx.tenant_id/user_id (not permissions or
    # branding), so placeholder values are fine — this ctx isn't going through a
    # require_permission() check or rendered in a template.
    ctx = TenantContext(
        tenant_id=tenant.id,
        user_id=users["approver"].id,
        security_group_id=uuid.uuid4(),
        permissions=frozenset(),
        tenant_slug=tenant.slug,
        tenant_name=tenant.name,
        accent_color=None,
        has_logo=False,
        has_favicon=False,
        customer_id=None,
        customer_name=None,
    )
    result = decision_service.decide(
        db_session, tenant.id, exception.id, ctx, outcome=outcome, reason_code="test", notes=None
    )
    db_session.commit()
    return result


def test_train_model_raises_below_minimum_decision_count(db_session, tenant_factory):
    from pospay.ml.train import InsufficientTrainingData, train_model

    tenant, _account, _users = tenant_factory.make(slug="ml-insufficient")

    with pytest.raises(InsufficientTrainingData):
        train_model(db_session, "check")


def test_score_exception_returns_none_before_any_model_trained(db_session, tenant_factory):
    from pospay.ml.predict import reset_model_cache, score_exception

    reset_model_cache()
    tenant, account, users = tenant_factory.make(slug="ml-cold-start")
    exception = _make_exception(db_session, tenant, account, users, "9101", "100.00", "999.00")

    score = score_exception(db_session, exception)

    assert score is None
    assert exception.ml_score is None


def test_train_then_score_populates_ml_score_on_new_exceptions(db_session, tenant_factory):
    from pospay.ml.predict import reset_model_cache, score_exception
    from pospay.ml.train import train_model

    reset_model_cache()
    tenant, account, users = tenant_factory.make(slug="ml-train-score", require_dual_control=False)

    # Generate 12 labeled decisions (above MIN_DECISIONS_TO_TRAIN=10), alternating
    # outcomes so both classes are present for a meaningful holdout split.
    for i in range(12):
        exception = _make_exception(
            db_session, tenant, account, users, f"92{i:02d}", "100.00", "999.00" if i % 2 == 0 else "888.00"
        )
        outcome = DecisionOutcome.RETURN if i % 2 == 0 else DecisionOutcome.PAY
        result = _decide(db_session, tenant, users, exception, outcome)
        assert result.error is None

    train_result = train_model(db_session, "check")
    assert train_result.promoted is True
    assert train_result.model_row.trained_from_decision_count == 12

    new_exception = _make_exception(db_session, tenant, account, users, "9301", "100.00", "999.00")
    score = score_exception(db_session, new_exception)

    assert score is not None
    assert 0.0 <= score <= 1.0
    assert new_exception.ml_model_version == train_result.model_row.version


def test_retrain_job_skips_networks_below_threshold(db_session, tenant_factory, monkeypatch):
    from pospay.workers.tasks import retrain_job

    tenant, account, users = tenant_factory.make(slug="ml-retrain-job-skip")
    _make_exception(db_session, tenant, account, users, "9401", "100.00", "999.00")

    # Only 1 decision exists, well below the default threshold (20) — must not raise,
    # just skip. Bind the job to the same in-memory engine the test uses.
    import pospay.db.session as db_session_module

    monkeypatch.setattr(db_session_module, "get_session_factory", lambda: lambda: db_session)
    # get_session_factory() normally returns a *callable* that produces a session; patch
    # it to return a zero-arg callable yielding this test's db_session directly.
    retrain_job()  # should complete without raising despite no active model / low data
