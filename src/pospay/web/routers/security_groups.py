import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from pospay.auth.permissions import PERMISSION_CATALOG
from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.services import audit_log_service, security_group_service
from pospay.web.deps import WebNotFound, render_template, require_web_permission
from pospay.web.security import verify_csrf

router = APIRouter(prefix="/ui/security-groups", tags=["web-security-groups"])


@router.get("")
def list_security_groups(
    request: Request, db: Session = Depends(get_db), ctx: TenantContext = Depends(require_web_permission("security_group:manage"))
) -> HTMLResponse:
    groups = security_group_service.list_security_groups(db, ctx.tenant_id)
    return render_template(
        request, "security_groups/list.html", ctx=ctx, groups=groups, catalog_size=len(PERMISSION_CATALOG)
    )


@router.get("/new")
def new_security_group_form(
    request: Request, ctx: TenantContext = Depends(require_web_permission("security_group:manage"))
) -> HTMLResponse:
    return render_template(
        request, "security_groups/form.html", ctx=ctx, catalog=PERMISSION_CATALOG, group=None, selected=set()
    )


@router.post("")
def create_security_group(
    request: Request,
    name: str = Form(...),
    permissions: list[str] = Form([]),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("security_group:manage")),
    _csrf: None = Depends(verify_csrf),
) -> RedirectResponse:
    group = security_group_service.create_security_group(
        db, ctx.tenant_id, security_group_service.SecurityGroupInput(name=name, permissions=permissions)
    )
    audit_log_service.record_action(
        db,
        ctx.tenant_id,
        actor_user_id=ctx.user_id,
        channel="web",
        action="security_group.create",
        summary=f"Created security group {group.name} ({len(group.permissions)} permissions)",
        resource_type="security_group",
        resource_id=group.id,
    )
    db.commit()
    return RedirectResponse("/ui/security-groups?flash=Security+group+created.", status_code=303)


@router.get("/{group_id}/edit")
def edit_security_group_form(
    request: Request,
    group_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("security_group:manage")),
) -> HTMLResponse:
    group = security_group_service.get_security_group(db, ctx.tenant_id, group_id)
    if group is None:
        raise WebNotFound()
    return render_template(
        request, "security_groups/form.html", ctx=ctx, catalog=PERMISSION_CATALOG, group=group, selected=set(group.permissions)
    )


@router.post("/{group_id}")
def update_security_group(
    request: Request,
    group_id: uuid.UUID,
    name: str = Form(...),
    permissions: list[str] = Form([]),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("security_group:manage")),
    _csrf: None = Depends(verify_csrf),
) -> RedirectResponse:
    group = security_group_service.update_security_group(
        db, ctx.tenant_id, group_id, security_group_service.SecurityGroupInput(name=name, permissions=permissions)
    )
    if group is not None:
        audit_log_service.record_action(
            db,
            ctx.tenant_id,
            actor_user_id=ctx.user_id,
            channel="web",
            action="security_group.update",
            summary=f"Updated security group {group.name} ({len(group.permissions)} permissions)",
            resource_type="security_group",
            resource_id=group.id,
        )
    db.commit()
    if group is None:
        return RedirectResponse("/ui/security-groups?error=Security+group+not+found.", status_code=303)
    return RedirectResponse("/ui/security-groups?flash=Security+group+updated.", status_code=303)
