import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.networks.check.ingestion import PaidItemSubmission, ingest_paid_item
from pospay.repositories.paid_item_repo import PaidItemRepository
from pospay.services import account_service, audit_log_service
from pospay.web.deps import WebNotFound, render_template, require_web_permission
from pospay.web.security import verify_csrf

router = APIRouter(prefix="/ui/paid-items", tags=["web-paid-items"])


@router.get("")
def list_paid_items(
    request: Request, db: Session = Depends(get_db), ctx: TenantContext = Depends(require_web_permission("paid_item:read"))
) -> HTMLResponse:
    items = PaidItemRepository(db, ctx.tenant_id, ctx.customer_id).list()
    return render_template(request, "paid_items/list.html", ctx=ctx, items=items)


@router.get("/new")
def new_paid_item_form(
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("paid_item:write")),
) -> HTMLResponse:
    accounts = account_service.list_accounts(db, ctx.tenant_id, customer_id=ctx.customer_id)
    return render_template(request, "paid_items/form.html", ctx=ctx, accounts=accounts)


@router.post("")
def create_paid_item(
    request: Request,
    account_id: uuid.UUID = Form(...),
    check_number: str = Form(...),
    presented_amount: str = Form(...),
    presented_date: str = Form(...),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("paid_item:write")),
    _csrf: None = Depends(verify_csrf),
) -> HTMLResponse:
    try:
        parsed_amount = Decimal(presented_amount)
        parsed_date = date.fromisoformat(presented_date)
    except (InvalidOperation, ValueError):
        accounts = account_service.list_accounts(db, ctx.tenant_id, customer_id=ctx.customer_id)
        return render_template(
            request, "paid_items/form.html", ctx=ctx, accounts=accounts, error="Invalid amount or date.", status_code=422
        )

    try:
        item = ingest_paid_item(
            db,
            ctx.tenant_id,
            PaidItemSubmission(
                account_id=account_id, check_number=check_number, presented_amount=parsed_amount, presented_date=parsed_date
            ),
            scoped_customer_id=ctx.customer_id,
        )
    except Exception as exc:  # noqa: BLE001 — surface e.g. an out-of-scope account to the form
        db.rollback()
        accounts = account_service.list_accounts(db, ctx.tenant_id, customer_id=ctx.customer_id)
        return render_template(
            request, "paid_items/form.html", ctx=ctx, accounts=accounts, error=f"Could not submit paid item: {exc}", status_code=422
        )
    audit_log_service.record_action(
        db,
        ctx.tenant_id,
        actor_user_id=ctx.user_id,
        channel="web",
        action="paid_item.create",
        summary=f"Presented check #{item.check_number} for {item.presented_amount}",
        resource_type="paid_item",
        resource_id=item.id,
    )
    db.commit()

    flash = "Paid item matched." if item.match_status.value == "matched" else "Paid item created an exception — see the Exceptions queue."
    return RedirectResponse(f"/ui/paid-items/{item.id}?flash={quote(flash)}", status_code=303)


@router.get("/{item_id}")
def paid_item_detail(
    request: Request,
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("paid_item:read")),
) -> HTMLResponse:
    item = PaidItemRepository(db, ctx.tenant_id, ctx.customer_id).get(item_id)
    if item is None:
        raise WebNotFound()
    return render_template(request, "paid_items/detail.html", ctx=ctx, item=item)
