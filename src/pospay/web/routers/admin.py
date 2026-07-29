# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.domain.customer_ml_setting import MlScoringMode
from pospay.domain.ml_model import MlModel
from pospay.ml.registry import activate_model
from pospay.ml.train import InsufficientTrainingData, RetrainCooldownActive, train_model
from pospay.networks.registry import registered_codes
from pospay.services import customer_ml_service, customer_service
from pospay.web.deps import WebNotFound, render_template, require_web_permission
from pospay.web.security import verify_csrf

router = APIRouter(prefix="/ui/admin", tags=["web-admin"])


@router.get("")
def admin_home(
    request: Request, db: Session = Depends(get_db), ctx: TenantContext = Depends(require_web_permission("admin:manage"))
) -> HTMLResponse:
    # customer_id.is_(None) — the global, network-wide models only; each customer's own
    # models have their own dedicated page (see the customer ML routes below), since
    # mixing them in here would make this table meaningless for a tenant with many
    # customers.
    models = db.execute(
        select(MlModel).where(MlModel.customer_id.is_(None)).order_by(MlModel.network_code, MlModel.created_at.desc())
    ).scalars().all()
    return render_template(request, "admin/ml_models.html", ctx=ctx, models=models, networks=registered_codes())


@router.post("/ml/retrain")
def retrain(
    network_code: str = Form(...),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("admin:manage")),
    _csrf: None = Depends(verify_csrf),
) -> RedirectResponse:
    try:
        result = train_model(db, network_code)
    except (InsufficientTrainingData, RetrainCooldownActive) as exc:
        return RedirectResponse(f"/ui/admin?error={quote(str(exc))}", status_code=303)
    flash = f"Retrained {network_code}: promoted={result.promoted}, metrics={result.metrics}"
    return RedirectResponse(f"/ui/admin?flash={quote(flash)}", status_code=303)


@router.post("/ml/models/{model_id}/activate")
def activate(
    model_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("admin:manage")),
    _csrf: None = Depends(verify_csrf),
) -> RedirectResponse:
    try:
        activate_model(db, model_id, expected_customer_id=None)
    except ValueError as exc:
        db.rollback()
        return RedirectResponse(f"/ui/admin?error={quote(str(exc))}", status_code=303)
    db.commit()
    return RedirectResponse("/ui/admin?flash=Model+activated.", status_code=303)


def _get_customer_or_404(db: Session, tenant_id: uuid.UUID, customer_id: uuid.UUID):
    customer = customer_service.get_customer(db, tenant_id, customer_id)
    if customer is None:
        raise WebNotFound()
    return customer


@router.get("/customers/{customer_id}/ml")
def customer_ml_detail(
    request: Request,
    customer_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("admin:manage")),
) -> HTMLResponse:
    customer = _get_customer_or_404(db, ctx.tenant_id, customer_id)
    summary = customer_ml_service.get_ml_summary(db, ctx.tenant_id, customer_id)
    models = customer_ml_service.list_customer_models(db, customer_id)
    return render_template(
        request,
        "admin/customer_ml.html",
        ctx=ctx,
        customer=customer,
        summary=summary,
        models=models,
        modes=list(MlScoringMode),
    )


@router.post("/customers/{customer_id}/ml/mode")
def set_customer_ml_mode(
    customer_id: uuid.UUID,
    network_code: str = Form(...),
    mode: MlScoringMode = Form(...),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("admin:manage")),
    _csrf: None = Depends(verify_csrf),
) -> RedirectResponse:
    _get_customer_or_404(db, ctx.tenant_id, customer_id)
    customer_ml_service.set_mode(db, ctx.tenant_id, customer_id, network_code, mode)
    db.commit()
    return RedirectResponse(f"/ui/admin/customers/{customer_id}/ml?flash=Scoring+mode+updated.", status_code=303)


@router.post("/customers/{customer_id}/ml/retrain")
def retrain_customer_model(
    customer_id: uuid.UUID,
    network_code: str = Form(...),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("admin:manage")),
    _csrf: None = Depends(verify_csrf),
) -> RedirectResponse:
    _get_customer_or_404(db, ctx.tenant_id, customer_id)
    try:
        result = train_model(db, network_code, customer_id=customer_id)
    except (InsufficientTrainingData, RetrainCooldownActive) as exc:
        return RedirectResponse(f"/ui/admin/customers/{customer_id}/ml?error={quote(str(exc))}", status_code=303)
    flash = f"Retrained {network_code}: promoted={result.promoted}, metrics={result.metrics}"
    return RedirectResponse(f"/ui/admin/customers/{customer_id}/ml?flash={quote(flash)}", status_code=303)


@router.post("/customers/{customer_id}/ml/models/{model_id}/activate")
def activate_customer_model(
    customer_id: uuid.UUID,
    model_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("admin:manage")),
    _csrf: None = Depends(verify_csrf),
) -> RedirectResponse:
    _get_customer_or_404(db, ctx.tenant_id, customer_id)
    try:
        activate_model(db, model_id, expected_customer_id=customer_id)
    except ValueError as exc:
        db.rollback()
        return RedirectResponse(f"/ui/admin/customers/{customer_id}/ml?error={quote(str(exc))}", status_code=303)
    db.commit()
    return RedirectResponse(f"/ui/admin/customers/{customer_id}/ml?flash=Model+activated.", status_code=303)
