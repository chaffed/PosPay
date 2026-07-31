# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.domain.exception_item import ExceptionStatus
from pospay.domain.issued_item import IssuedItemStatus
from pospay.domain.stop_payment import StopPaymentStatus
from pospay.repositories.exception_repo import ExceptionRepository
from pospay.repositories.issued_item_repo import IssuedItemRepository
from pospay.repositories.stop_payment_repo import StopPaymentRepository
from pospay.services import security_group_service, wizard_service
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
    # TenantContext carries security_group_id (a UUID), not a display name — this is the
    # one place the dashboard needs the human-readable name, so resolve it here rather
    # than growing TenantContext for a single label.
    group = security_group_service.get_security_group(db, ctx.tenant_id, ctx.security_group_id)

    # Each count is gated on the same read permission its own list page requires, so a
    # role that can't see a resource at all doesn't get a stat card teasing its count
    # either — mirrors the "Admin" quick-link's existing can(ctx, ...) gating below.
    open_exceptions_count = None
    if "exception:read" in ctx.permissions:
        open_exceptions_count = ExceptionRepository(db, ctx.tenant_id, ctx.customer_id).count(status=ExceptionStatus.OPEN)
    outstanding_issued_items_count = None
    if "issued_item:read" in ctx.permissions:
        outstanding_issued_items_count = IssuedItemRepository(db, ctx.tenant_id, ctx.customer_id).count(
            status=IssuedItemStatus.OUTSTANDING
        )
    active_stop_payments_count = None
    if "stop_payment:read" in ctx.permissions:
        active_stop_payments_count = StopPaymentRepository(db, ctx.tenant_id, ctx.customer_id).count(
            status=StopPaymentStatus.ACTIVE
        )

    return render_template(
        request, "dashboard.html", ctx=ctx, show_getting_started=show_getting_started,
        security_group_name=group.name if group else None,
        open_exceptions_count=open_exceptions_count,
        outstanding_issued_items_count=outstanding_issued_items_count,
        active_stop_payments_count=active_stop_payments_count,
    )
