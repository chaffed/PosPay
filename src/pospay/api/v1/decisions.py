# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from pospay.auth.deps import require_permission
from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.schemas.decision import DecideRequest, DecisionRead, RecommendRequest
from pospay.schemas.exception import ExceptionRead
from pospay.services import audit_log_service, decision_service
from pospay.services.decision_service import DecisionError

router = APIRouter(prefix="/exceptions", tags=["decisions"])

_ERROR_STATUS = {
    DecisionError.NOT_FOUND: status.HTTP_404_NOT_FOUND,
    DecisionError.ALREADY_DECIDED: status.HTTP_409_CONFLICT,
    DecisionError.RECOMMENDATION_REQUIRED: status.HTTP_409_CONFLICT,
    DecisionError.MAKER_CANNOT_APPROVE_OWN_RECOMMENDATION: status.HTTP_403_FORBIDDEN,
}


@router.post("/{exception_id}/recommend", response_model=ExceptionRead)
def recommend_decision(
    exception_id: uuid.UUID,
    payload: RecommendRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("exception:recommend")),
) -> ExceptionRead:
    result = decision_service.submit_recommendation(
        db,
        ctx.tenant_id,
        exception_id,
        ctx,
        outcome=payload.outcome,
        reason_code=payload.reason_code,
        notes=payload.notes,
    )
    if result.error is not None:
        raise HTTPException(_ERROR_STATUS[result.error], result.error.value)
    audit_log_service.record_action(
        db,
        ctx.tenant_id,
        actor_user_id=ctx.user_id,
        channel="api",
        action="exception.recommend",
        summary=f"Recommended {payload.outcome.value} on exception ({payload.reason_code})",
        resource_type="exception_item",
        resource_id=exception_id,
    )
    db.commit()
    return ExceptionRead.from_orm_row(result.exception)


@router.post("/{exception_id}/decide", response_model=DecisionRead)
def decide_exception(
    exception_id: uuid.UUID,
    payload: DecideRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("exception:decide")),
) -> DecisionRead:
    result = decision_service.decide(
        db,
        ctx.tenant_id,
        exception_id,
        ctx,
        outcome=payload.outcome,
        reason_code=payload.reason_code,
        notes=payload.notes,
    )
    if result.error is not None:
        raise HTTPException(_ERROR_STATUS[result.error], result.error.value)
    audit_log_service.record_action(
        db,
        ctx.tenant_id,
        actor_user_id=ctx.user_id,
        channel="api",
        action="exception.decide",
        summary=f"Decided {payload.outcome.value} on exception ({payload.reason_code})",
        resource_type="exception_item",
        resource_id=exception_id,
    )
    db.commit()
    return DecisionRead.model_validate(result.decision)


@router.get("/{exception_id}/decision", response_model=DecisionRead)
def get_decision(
    exception_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("exception:read")),
) -> DecisionRead:
    decision = decision_service.get_decision_for_exception(db, ctx.tenant_id, exception_id)
    if decision is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No decision recorded for this exception")
    return DecisionRead.model_validate(decision)
