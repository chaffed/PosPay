# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from pospay.auth.deps import require_permission
from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.domain.ml_model import MlModel
from pospay.ml.registry import activate_model
from pospay.ml.train import InsufficientTrainingData, RetrainCooldownActive, train_model
from pospay.networks.registry import registered_codes
from pospay.schemas.ml_model import MlModelRead, RetrainResponse

router = APIRouter(prefix="/admin", tags=["admin"])

# NOTE: ml_model rows are global-per-network (see domain/ml_model.py — no tenant_id
# column, matching the plan's "global model, tenant_id as a feature" decision to solve
# cold start). That means these endpoints, gated on "admin:manage", let ANY tenant's
# admin retrain/activate a model that scores every tenant's exceptions. For a real
# multi-tenant deployment this should be restricted to a platform-level super-admin role,
# not a per-tenant ADMIN — flagged here rather than silently shipped as tenant-scoped.


@router.get("/payment-networks", response_model=list[str])
def list_payment_networks(ctx: TenantContext = Depends(require_permission("admin:manage"))) -> list[str]:
    return registered_codes()


@router.post("/ml/retrain", response_model=RetrainResponse)
def retrain(
    network_code: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("admin:manage")),
) -> RetrainResponse:
    try:
        result = train_model(db, network_code)
    except (InsufficientTrainingData, RetrainCooldownActive) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None

    return RetrainResponse(
        network_code=network_code,
        promoted=result.promoted,
        metrics=result.metrics,
        model=MlModelRead.model_validate(result.model_row),
    )


@router.get("/ml/models", response_model=list[MlModelRead])
def list_ml_models(
    network_code: str | None = None,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("admin:manage")),
) -> list[MlModelRead]:
    stmt = select(MlModel)
    if network_code is not None:
        stmt = stmt.where(MlModel.network_code == network_code)
    rows = db.execute(stmt).scalars().all()
    return [MlModelRead.model_validate(r) for r in rows]


@router.patch("/ml/models/{model_id}/activate", response_model=MlModelRead)
def activate_ml_model(
    model_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("admin:manage")),
) -> MlModelRead:
    try:
        model = activate_model(db, model_id, expected_customer_id=None)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    db.commit()
    return MlModelRead.model_validate(model)
