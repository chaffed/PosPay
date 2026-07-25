from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.services import audit_log_service
from pospay.services.tenant_service import InvalidBrandingInput, update_tenant_branding
from pospay.web.deps import render_template, require_web_permission
from pospay.web.security import verify_csrf

router = APIRouter(prefix="/ui/settings", tags=["web-tenant-settings"])


@router.get("")
def settings_form(
    request: Request, ctx: TenantContext = Depends(require_web_permission("tenant:manage"))
) -> HTMLResponse:
    return render_template(
        request, "settings/form.html", ctx=ctx, tenant_display_name=ctx.tenant_name, accent_color=ctx.accent_color or ""
    )


@router.post("")
async def update_settings(
    request: Request,
    name: str = Form(...),
    accent_color: str = Form(""),
    logo: UploadFile | None = File(None),
    favicon: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("tenant:manage")),
    _csrf: None = Depends(verify_csrf),
) -> HTMLResponse:
    # An <input type="file"> left empty still submits a (filename-less) part in a
    # multipart form — that's "no new file", not "an empty file"; only treat it as a
    # replacement when a filename is actually present.
    logo_data = (logo.content_type or "application/octet-stream", await logo.read()) if logo and logo.filename else None
    favicon_data = (
        (favicon.content_type or "application/octet-stream", await favicon.read()) if favicon and favicon.filename else None
    )

    try:
        tenant = update_tenant_branding(
            db, ctx.tenant_id, name=name, accent_color=accent_color or None, logo=logo_data, favicon=favicon_data
        )
    except InvalidBrandingInput as exc:
        db.rollback()
        return render_template(
            request,
            "settings/form.html",
            ctx=ctx,
            tenant_display_name=name,
            accent_color=accent_color,
            error=str(exc),
            status_code=422,
        )

    if tenant is not None:
        audit_log_service.record_action(
            db,
            ctx.tenant_id,
            actor_user_id=ctx.user_id,
            channel="web",
            action="tenant.update_settings",
            summary=f"Updated organization settings (name: {tenant.name})",
            resource_type="tenant",
            resource_id=ctx.tenant_id,
        )
    db.commit()
    return RedirectResponse("/ui/settings?flash=Settings+updated.", status_code=303)
