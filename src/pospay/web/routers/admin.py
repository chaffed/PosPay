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
from pospay.domain.ml_model import MlModel
from pospay.ml.registry import activate_model
from pospay.ml.train import InsufficientTrainingData, train_model
from pospay.networks.registry import registered_codes
from pospay.web.deps import render_template, require_web_permission
from pospay.web.security import verify_csrf

router = APIRouter(prefix="/ui/admin", tags=["web-admin"])


@router.get("")
def admin_home(
    request: Request, db: Session = Depends(get_db), ctx: TenantContext = Depends(require_web_permission("admin:manage"))
) -> HTMLResponse:
    models = db.execute(select(MlModel).order_by(MlModel.network_code, MlModel.created_at.desc())).scalars().all()
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
    except InsufficientTrainingData as exc:
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
        activate_model(db, model_id)
    except ValueError as exc:
        db.rollback()
        return RedirectResponse(f"/ui/admin?error={quote(str(exc))}", status_code=303)
    db.commit()
    return RedirectResponse("/ui/admin?flash=Model+activated.", status_code=303)
