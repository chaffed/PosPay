# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import enum
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from pospay.db.tenancy import TenantContext
from pospay.domain.decision import Decision, DecisionOutcome
from pospay.domain.exception_item import ExceptionItem, ExceptionStatus
from pospay.domain.tenant import Tenant
from pospay.networks.registry import get_adapter
from pospay.repositories.decision_repo import DecisionRepository
from pospay.repositories.exception_repo import ExceptionRepository


class DecisionError(str, enum.Enum):
    NOT_FOUND = "not_found"
    ALREADY_DECIDED = "already_decided"
    RECOMMENDATION_REQUIRED = "recommendation_required"
    MAKER_CANNOT_APPROVE_OWN_RECOMMENDATION = "maker_cannot_approve_own_recommendation"
    WITHDRAWN = "withdrawn"


@dataclass(frozen=True, slots=True)
class ServiceResult:
    decision: Decision | None
    exception: ExceptionItem | None
    error: DecisionError | None


def submit_recommendation(
    session: Session,
    tenant_id: uuid.UUID,
    exception_id: uuid.UUID,
    ctx: TenantContext,
    *,
    outcome: DecisionOutcome,
    reason_code: str,
    notes: str | None,
) -> ServiceResult:
    repo = ExceptionRepository(session, tenant_id)
    exception = repo.get(exception_id)
    if exception is None:
        return ServiceResult(None, None, DecisionError.NOT_FOUND)
    if exception.status == ExceptionStatus.WITHDRAWN:
        return ServiceResult(None, None, DecisionError.WITHDRAWN)
    if exception.status not in (ExceptionStatus.OPEN, ExceptionStatus.PENDING_APPROVAL):
        return ServiceResult(None, None, DecisionError.ALREADY_DECIDED)

    exception.recommended_outcome = outcome.value
    exception.recommended_reason_code = reason_code
    exception.recommended_notes = notes
    exception.recommended_by_user_id = ctx.user_id
    exception.status = ExceptionStatus.PENDING_APPROVAL
    session.flush()
    return ServiceResult(None, exception, None)


def decide(
    session: Session,
    tenant_id: uuid.UUID,
    exception_id: uuid.UUID,
    ctx: TenantContext,
    *,
    outcome: DecisionOutcome,
    reason_code: str,
    notes: str | None,
) -> ServiceResult:
    """Records the final pay/return decision — this is the ML feedback point. Under
    dual-control tenants, requires a prior recommend() from a *different* user (maker !=
    checker is enforced here, not just in the UI)."""
    tenant = session.get(Tenant, tenant_id)
    exception_repo = ExceptionRepository(session, tenant_id)
    exception = exception_repo.get(exception_id)
    if exception is None:
        return ServiceResult(None, None, DecisionError.NOT_FOUND)
    if exception.status == ExceptionStatus.WITHDRAWN:
        return ServiceResult(None, None, DecisionError.WITHDRAWN)
    if exception.status in (ExceptionStatus.PAY, ExceptionStatus.RETURN):
        return ServiceResult(None, None, DecisionError.ALREADY_DECIDED)

    submitted_by_user_id: uuid.UUID | None = None
    if tenant.require_dual_control:
        if exception.status != ExceptionStatus.PENDING_APPROVAL:
            return ServiceResult(None, None, DecisionError.RECOMMENDATION_REQUIRED)
        if exception.recommended_by_user_id == ctx.user_id:
            return ServiceResult(None, None, DecisionError.MAKER_CANNOT_APPROVE_OWN_RECOMMENDATION)
        submitted_by_user_id = exception.recommended_by_user_id

    adapter = get_adapter(exception.network_code)
    features = adapter.build_features(session, exception)

    decision_repo = DecisionRepository(session, tenant_id)
    decision = Decision(
        exception_item_id=exception.id,
        outcome=outcome,
        reason_code=reason_code,
        notes=notes,
        submitted_by_user_id=submitted_by_user_id,
        decided_by_user_id=ctx.user_id,
        features_json=features,
    )
    decision_repo.add(decision)

    exception.status = ExceptionStatus.PAY if outcome == DecisionOutcome.PAY else ExceptionStatus.RETURN
    session.flush()
    return ServiceResult(decision, exception, None)


def get_decision_for_exception(session: Session, tenant_id: uuid.UUID, exception_id: uuid.UUID) -> Decision | None:
    repo = DecisionRepository(session, tenant_id)
    results = repo.list(exception_item_id=exception_id)
    return results[0] if results else None
