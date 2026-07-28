import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.services import account_service, audit_log_service, stop_payment_service
from pospay.web.deps import render_template, require_web_permission
from pospay.web.security import verify_csrf

router = APIRouter(prefix="/ui/stop-payments", tags=["web-stop-payments"])


@router.get("")
def list_stop_payments(
    request: Request, db: Session = Depends(get_db), ctx: TenantContext = Depends(require_web_permission("stop_payment:read"))
) -> HTMLResponse:
    stops = stop_payment_service.list_stop_payments(db, ctx.tenant_id, customer_id=ctx.customer_id)
    return render_template(request, "stop_payments/list.html", ctx=ctx, stops=stops)


@router.get("/new")
def new_stop_payment_form(
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("stop_payment:write")),
) -> HTMLResponse:
    accounts = account_service.list_accounts(db, ctx.tenant_id, customer_id=ctx.customer_id)
    return render_template(request, "stop_payments/form.html", ctx=ctx, accounts=accounts)


@router.post("")
def create_stop_payment(
    request: Request,
    account_id: uuid.UUID = Form(...),
    check_number: str = Form(...),
    amount: str = Form(""),
    effective_date: str = Form(...),
    expiration_date: str = Form(""),
    reason: str = Form(""),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("stop_payment:write")),
    _csrf: None = Depends(verify_csrf),
) -> HTMLResponse:
    try:
        parsed_amount = Decimal(amount) if amount else None
        parsed_effective = date.fromisoformat(effective_date)
        parsed_expiration = date.fromisoformat(expiration_date) if expiration_date else None
    except (InvalidOperation, ValueError):
        accounts = account_service.list_accounts(db, ctx.tenant_id, customer_id=ctx.customer_id)
        return render_template(
            request, "stop_payments/form.html", ctx=ctx, accounts=accounts, error="Invalid amount or date.", status_code=422
        )

    try:
        stop = stop_payment_service.create_stop_payment(
            db,
            ctx.tenant_id,
            stop_payment_service.StopPaymentInput(
                account_id=account_id,
                check_number=check_number,
                amount=parsed_amount,
                effective_date=parsed_effective,
                expiration_date=parsed_expiration,
                reason=reason or None,
            ),
            created_by_user_id=ctx.user_id,
            scoped_customer_id=ctx.customer_id,
        )
    except Exception as exc:  # noqa: BLE001 — surface e.g. an out-of-scope account to the form
        db.rollback()
        accounts = account_service.list_accounts(db, ctx.tenant_id, customer_id=ctx.customer_id)
        return render_template(
            request,
            "stop_payments/form.html",
            ctx=ctx,
            accounts=accounts,
            error=f"Could not create stop payment: {exc}",
            status_code=422,
        )
    audit_log_service.record_action(
        db,
        ctx.tenant_id,
        actor_user_id=ctx.user_id,
        channel="web",
        action="stop_payment.create",
        summary=f"Stopped payment on check #{stop.check_number}" + (f": {reason}" if reason else ""),
        resource_type="stop_payment",
        resource_id=stop.id,
    )
    db.commit()
    return RedirectResponse("/ui/stop-payments?flash=Stop+payment+created.", status_code=303)


@router.post("/{stop_id}/cancel")
def cancel_stop_payment(
    stop_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("stop_payment:write")),
    _csrf: None = Depends(verify_csrf),
) -> RedirectResponse:
    stop = stop_payment_service.cancel_stop_payment(db, ctx.tenant_id, stop_id, scoped_customer_id=ctx.customer_id)
    if stop is not None:
        audit_log_service.record_action(
            db,
            ctx.tenant_id,
            actor_user_id=ctx.user_id,
            channel="web",
            action="stop_payment.cancel",
            summary=f"Cancelled stop payment on check #{stop.check_number}",
            resource_type="stop_payment",
            resource_id=stop.id,
        )
    db.commit()
    return RedirectResponse("/ui/stop-payments?flash=Stop+payment+cancelled.", status_code=303)
