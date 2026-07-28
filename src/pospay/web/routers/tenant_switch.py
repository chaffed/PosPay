import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from pospay.auth.security import create_token
from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.services import user_service
from pospay.web.deps import get_web_context, render_template
from pospay.web.security import set_access_cookie, set_refresh_cookie, verify_csrf

router = APIRouter(prefix="/ui/switch-tenant", tags=["web-tenant-switch"])


@router.get("")
def switch_tenant_form(
    request: Request, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_web_context)
) -> HTMLResponse:
    """Also doubles as "switch customer scope" — a user can now hold several
    memberships within the same tenant (one per customer, or tenant-wide plus
    per-customer overrides), so the current one is excluded by its exact
    (tenant_id, customer_id) pair, not just by tenant_id."""
    memberships = [
        m
        for m in user_service.list_memberships_for_user(db, ctx.user_id)
        if not (m.membership.tenant_id == ctx.tenant_id and m.membership.customer_id == ctx.customer_id)
    ]
    return render_template(request, "tenant_switch.html", ctx=ctx, memberships=memberships)


@router.post("")
def switch_tenant(
    membership_id: uuid.UUID = Form(...),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_web_context),
    _csrf: None = Depends(verify_csrf),
) -> RedirectResponse:
    """No password or WebAuthn re-entry — the caller already holds a valid session for
    this identity; this only re-validates that the identity actually holds the target
    membership, then mints tokens scoped to it (tenant, and — new — customer). Keyed on
    the membership's own id rather than tenant_id, since more than one membership can now
    share a tenant_id (see domain/tenant_membership.py)."""
    target = next(
        (m for m in user_service.list_memberships_for_user(db, ctx.user_id) if m.membership.id == membership_id), None
    )
    if target is None:
        return RedirectResponse("/ui/switch-tenant?error=Not+a+member+of+that+organization.", status_code=303)

    access_token = create_token(
        user_id=ctx.user_id,
        tenant_id=target.tenant.id,
        security_group_id=target.membership.security_group_id,
        customer_id=target.membership.customer_id,
        token_type="access",
    )
    refresh_token = create_token(
        user_id=ctx.user_id,
        tenant_id=target.tenant.id,
        security_group_id=target.membership.security_group_id,
        customer_id=target.membership.customer_id,
        token_type="refresh",
    )
    response = RedirectResponse("/ui/", status_code=303)
    set_access_cookie(response, access_token)
    set_refresh_cookie(response, refresh_token)
    return response
