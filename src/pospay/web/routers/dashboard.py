# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.services import wizard_service
from pospay.web.deps import get_web_context, render_template

router = APIRouter(prefix="/ui", tags=["web-dashboard"])


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_web_context)) -> HTMLResponse:
    # Only bank-wide admins can act on the bank wizard's steps, and customer-scoped
    # sessions don't have a single tenant-wide "getting started" state to show anyway.
    show_getting_started = (
        ctx.customer_id is None
        and "tenant:manage" in ctx.permissions
        and not wizard_service.is_bank_wizard_complete(db, ctx.tenant_id)
    )
    return render_template(request, "dashboard.html", ctx=ctx, show_getting_started=show_getting_started)
