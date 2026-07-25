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
    memberships = [m for m in user_service.list_memberships_for_user(db, ctx.user_id) if m.tenant.id != ctx.tenant_id]
    return render_template(request, "tenant_switch.html", ctx=ctx, memberships=memberships)


@router.post("")
def switch_tenant(
    tenant_id: uuid.UUID = Form(...),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_web_context),
    _csrf: None = Depends(verify_csrf),
) -> RedirectResponse:
    """No password or WebAuthn re-entry — the caller already holds a valid session for
    this identity; this only re-validates that the identity has an active membership in
    the target tenant, then mints tokens scoped to it (see plan: cross-tenant access is
    one identity holding multiple tenant memberships, switchable after login)."""
    target = next(
        (m for m in user_service.list_memberships_for_user(db, ctx.user_id) if m.tenant.id == tenant_id), None
    )
    if target is None:
        return RedirectResponse("/ui/switch-tenant?error=Not+a+member+of+that+organization.", status_code=303)

    access_token = create_token(
        user_id=ctx.user_id, tenant_id=tenant_id, security_group_id=target.membership.security_group_id, token_type="access"
    )
    refresh_token = create_token(
        user_id=ctx.user_id, tenant_id=tenant_id, security_group_id=target.membership.security_group_id, token_type="refresh"
    )
    response = RedirectResponse("/ui/", status_code=303)
    set_access_cookie(response, access_token)
    set_refresh_cookie(response, refresh_token)
    return response
