import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.services import account_service, ach_authorization_service, audit_log_service
from pospay.web.deps import render_template, require_web_permission
from pospay.web.security import verify_csrf

router = APIRouter(prefix="/ui/ach/authorizations", tags=["web-ach-authorizations"])


@router.get("")
def list_authorizations(
    request: Request, db: Session = Depends(get_db), ctx: TenantContext = Depends(require_web_permission("ach_authorization:read"))
) -> HTMLResponse:
    rules = ach_authorization_service.list_ach_authorizations(db, ctx.tenant_id, customer_id=ctx.customer_id)
    return render_template(request, "ach/authorizations_list.html", ctx=ctx, rules=rules)


@router.get("/new")
def new_authorization_form(
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("ach_authorization:write")),
) -> HTMLResponse:
    accounts = account_service.list_accounts(db, ctx.tenant_id, customer_id=ctx.customer_id)
    return render_template(request, "ach/authorization_form.html", ctx=ctx, accounts=accounts)


@router.post("")
def create_authorization(
    request: Request,
    account_id: uuid.UUID = Form(...),
    originator_id: str = Form(...),
    originator_name: str = Form(...),
    receiver_id: str = Form(""),
    max_amount: str = Form(""),
    frequency_limit: str = Form(""),
    allowed_sec_codes: str = Form(""),
    effective_date: str = Form(...),
    expiration_date: str = Form(""),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("ach_authorization:write")),
    _csrf: None = Depends(verify_csrf),
) -> HTMLResponse:
    try:
        parsed_max_amount = Decimal(max_amount) if max_amount else None
        parsed_frequency_limit = int(frequency_limit) if frequency_limit else None
        parsed_effective = date.fromisoformat(effective_date)
        parsed_expiration = date.fromisoformat(expiration_date) if expiration_date else None
        parsed_sec_codes = [c.strip().upper() for c in allowed_sec_codes.split(",") if c.strip()] or None
    except (InvalidOperation, ValueError):
        accounts = account_service.list_accounts(db, ctx.tenant_id, customer_id=ctx.customer_id)
        return render_template(
            request, "ach/authorization_form.html", ctx=ctx, accounts=accounts, error="Invalid input.", status_code=422
        )

    try:
        rule = ach_authorization_service.create_ach_authorization(
            db,
            ctx.tenant_id,
            ach_authorization_service.AchAuthorizationInput(
                account_id=account_id,
                originator_id=originator_id,
                originator_name=originator_name,
                receiver_id=receiver_id or None,
                max_amount=parsed_max_amount,
                frequency_limit=parsed_frequency_limit,
                allowed_sec_codes=parsed_sec_codes,
                effective_date=parsed_effective,
                expiration_date=parsed_expiration,
            ),
            created_by_user_id=ctx.user_id,
            scoped_customer_id=ctx.customer_id,
        )
    except Exception as exc:  # noqa: BLE001 — surface e.g. an out-of-scope account to the form
        db.rollback()
        accounts = account_service.list_accounts(db, ctx.tenant_id, customer_id=ctx.customer_id)
        return render_template(
            request, "ach/authorization_form.html", ctx=ctx, accounts=accounts, error=f"Could not create authorization: {exc}", status_code=422
        )
    audit_log_service.record_action(
        db,
        ctx.tenant_id,
        actor_user_id=ctx.user_id,
        channel="web",
        action="ach_authorization.create",
        summary=f"Authorized ACH originator {rule.originator_name} ({rule.originator_id})",
        resource_type="ach_authorization",
        resource_id=rule.id,
    )
    db.commit()
    return RedirectResponse("/ui/ach/authorizations?flash=Authorization+created.", status_code=303)


@router.post("/{rule_id}/revoke")
def revoke_authorization(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("ach_authorization:write")),
    _csrf: None = Depends(verify_csrf),
) -> RedirectResponse:
    rule = ach_authorization_service.revoke_ach_authorization(db, ctx.tenant_id, rule_id, scoped_customer_id=ctx.customer_id)
    if rule is not None:
        audit_log_service.record_action(
            db,
            ctx.tenant_id,
            actor_user_id=ctx.user_id,
            channel="web",
            action="ach_authorization.revoke",
            summary=f"Revoked ACH authorization for {rule.originator_name} ({rule.originator_id})",
            resource_type="ach_authorization",
            resource_id=rule.id,
        )
    db.commit()
    return RedirectResponse("/ui/ach/authorizations?flash=Authorization+revoked.", status_code=303)
