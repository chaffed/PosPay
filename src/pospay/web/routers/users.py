import uuid

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from pospay.bulk_import.tabular import TabularParseError, parse_tabular_file
from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.domain.bulk_upload_file import BulkUploadKind
from pospay.repositories.user_repo import UserRepository
from pospay.services import audit_log_service, bulk_upload_file_service, security_group_service, user_service
from pospay.web.deps import render_template, require_web_permission
from pospay.web.security import verify_csrf

router = APIRouter(prefix="/ui/users", tags=["web-users"])


@router.get("")
def list_users(
    request: Request, db: Session = Depends(get_db), ctx: TenantContext = Depends(require_web_permission("user:manage"))
) -> HTMLResponse:
    rows = user_service.list_tenant_users(db, ctx.tenant_id)
    return render_template(request, "users/list.html", ctx=ctx, rows=rows)


@router.get("/new")
def new_user_form(
    request: Request, db: Session = Depends(get_db), ctx: TenantContext = Depends(require_web_permission("user:manage"))
) -> HTMLResponse:
    groups = security_group_service.list_security_groups(db, ctx.tenant_id)
    return render_template(request, "users/new.html", ctx=ctx, groups=groups)


@router.post("")
def create_user(
    request: Request,
    email: str = Form(...),
    password: str = Form(""),
    security_group_id: uuid.UUID = Form(...),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("user:manage")),
    _csrf: None = Depends(verify_csrf),
) -> HTMLResponse:
    result = user_service.add_user(db, ctx.tenant_id, email=email, password=password, security_group_id=security_group_id)

    if result.outcome == "created":
        created_user = UserRepository(db).get_by_email(email)
        audit_log_service.record_action(
            db,
            ctx.tenant_id,
            actor_user_id=ctx.user_id,
            channel="web",
            action="user.create",
            summary=f"Added user {email}",
            resource_type="user",
            resource_id=created_user.id if created_user else None,
        )
        db.commit()
        return RedirectResponse("/ui/users?flash=User+created.", status_code=303)
    if result.outcome == "already_member":
        db.rollback()
        return RedirectResponse("/ui/users?flash=That+person+already+has+access+to+this+organization.", status_code=303)
    if result.outcome == "needs_confirmation":
        db.rollback()
        group = security_group_service.get_security_group(db, ctx.tenant_id, security_group_id)
        return render_template(
            request,
            "users/confirm_existing.html",
            ctx=ctx,
            email=email,
            security_group_id=security_group_id,
            security_group_name=group.name if group else "",
        )

    db.rollback()
    groups = security_group_service.list_security_groups(db, ctx.tenant_id)
    return render_template(request, "users/new.html", ctx=ctx, groups=groups, error=result.error, status_code=422)


@router.post("/confirm")
def confirm_existing_user(
    email: str = Form(...),
    security_group_id: uuid.UUID = Form(...),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("user:manage")),
    _csrf: None = Depends(verify_csrf),
) -> RedirectResponse:
    membership = user_service.confirm_cross_tenant_membership(
        db, ctx.tenant_id, email=email, security_group_id=security_group_id
    )
    if membership is None:
        db.rollback()
        return RedirectResponse("/ui/users?error=That+user+no+longer+exists.", status_code=303)
    audit_log_service.record_action(
        db,
        ctx.tenant_id,
        actor_user_id=ctx.user_id,
        channel="web",
        action="user.grant_cross_tenant_access",
        summary=f"Granted {email} access to this organization",
        resource_type="user",
        resource_id=membership.user_id,
    )
    db.commit()
    return RedirectResponse("/ui/users?flash=Access+granted.", status_code=303)


@router.post("/{membership_id}/deactivate")
def deactivate_user(
    membership_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("user:manage")),
    _csrf: None = Depends(verify_csrf),
) -> RedirectResponse:
    membership = user_service.deactivate_membership(db, ctx.tenant_id, membership_id)
    if membership is not None:
        actor = UserRepository(db).get(membership.user_id)
        audit_log_service.record_action(
            db,
            ctx.tenant_id,
            actor_user_id=ctx.user_id,
            channel="web",
            action="user.deactivate",
            summary=f"Deactivated access for {actor.email if actor else membership.user_id}",
            resource_type="user",
            resource_id=membership.user_id,
        )
    db.commit()
    if membership is None:
        return RedirectResponse("/ui/users?error=User+not+found.", status_code=303)
    return RedirectResponse("/ui/users?flash=Access+removed.", status_code=303)


@router.post("/{membership_id}/reactivate")
def reactivate_user(
    membership_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("user:manage")),
    _csrf: None = Depends(verify_csrf),
) -> RedirectResponse:
    membership = user_service.reactivate_membership(db, ctx.tenant_id, membership_id)
    if membership is not None:
        actor = UserRepository(db).get(membership.user_id)
        audit_log_service.record_action(
            db,
            ctx.tenant_id,
            actor_user_id=ctx.user_id,
            channel="web",
            action="user.reactivate",
            summary=f"Restored access for {actor.email if actor else membership.user_id}",
            resource_type="user",
            resource_id=membership.user_id,
        )
    db.commit()
    if membership is None:
        return RedirectResponse("/ui/users?error=User+not+found.", status_code=303)
    return RedirectResponse("/ui/users?flash=Access+restored.", status_code=303)


@router.get("/bulk")
def bulk_upload_form(
    request: Request, ctx: TenantContext = Depends(require_web_permission("user:manage"))
) -> HTMLResponse:
    return render_template(request, "users/bulk_upload.html", ctx=ctx)


@router.post("/bulk")
async def bulk_upload_users(
    request: Request,
    upload_file: UploadFile,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("user:manage")),
    _csrf: None = Depends(verify_csrf),
) -> HTMLResponse:
    content = await upload_file.read()

    # Recorded before parsing (and committed on its own) so a rejected/malformed file is
    # still captured for audit purposes, not just successful uploads — see
    # services/bulk_upload_file_service.py.
    upload_record = bulk_upload_file_service.record_uploaded_file(
        db,
        ctx.tenant_id,
        kind=BulkUploadKind.USERS,
        filename=upload_file.filename or "upload.csv",
        content_type=upload_file.content_type,
        data=content,
        uploaded_by_user_id=ctx.user_id,
    )
    db.commit()

    try:
        rows = parse_tabular_file(upload_file.filename or "upload.csv", content)
    except TabularParseError as exc:
        return render_template(
            request, "users/bulk_upload.html", ctx=ctx, error=str(exc), status_code=422, upload_record=upload_record
        )
    if not rows:
        return render_template(
            request,
            "users/bulk_upload.html",
            ctx=ctx,
            error="That file has no data rows.",
            status_code=422,
            upload_record=upload_record,
        )

    results = user_service.create_users_from_rows(db, ctx.tenant_id, rows)
    for r in results:
        if r.outcome != "created":
            continue
        created_user = UserRepository(db).get_by_email(r.email) if r.email else None
        audit_log_service.record_action(
            db,
            ctx.tenant_id,
            actor_user_id=ctx.user_id,
            channel="web",
            action="user.create",
            summary=f"Added user {r.email} via bulk upload ({r.row_label})",
            resource_type="user",
            resource_id=created_user.id if created_user else None,
        )
    pending = []
    for r in results:
        if r.outcome != "needs_confirmation":
            continue
        group = security_group_service.get_security_group(db, ctx.tenant_id, r.security_group_id) if r.security_group_id else None
        pending.append({"email": r.email, "group_name": group.name if group else "", "value": f"{r.email}::{r.security_group_id}"})

    bulk_upload_file_service.set_result_counts(
        db,
        upload_record,
        succeeded_count=sum(r.outcome in ("created", "already_member") for r in results),
        failed_count=sum(r.outcome == "failed" for r in results),
    )
    db.commit()
    return render_template(
        request, "users/bulk_result.html", ctx=ctx, results=results, pending=pending, upload_record=upload_record
    )


@router.post("/bulk/confirm")
def bulk_confirm_users(
    request: Request,
    confirm: list[str] = Form([]),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("user:manage")),
    _csrf: None = Depends(verify_csrf),
) -> HTMLResponse:
    confirmations: list[tuple[str, uuid.UUID]] = []
    for value in confirm:
        email, _, group_id = value.partition("::")
        if email and group_id:
            confirmations.append((email, uuid.UUID(group_id)))

    results = user_service.confirm_users_bulk(db, ctx.tenant_id, confirmations)
    # confirm_users_bulk already committed each grant individually (per-row isolation,
    # same as every other bulk flow) — these audit entries land in a follow-up commit
    # of their own rather than the same transaction as the grant, the one exception to
    # this feature's usual "same transaction" rule, forced by that pre-existing pattern.
    for r in results:
        if r.outcome != "created":
            continue
        created_user = UserRepository(db).get_by_email(r.email) if r.email else None
        audit_log_service.record_action(
            db,
            ctx.tenant_id,
            actor_user_id=ctx.user_id,
            channel="web",
            action="user.grant_cross_tenant_access",
            summary=f"Granted {r.email} access to this organization (bulk confirm)",
            resource_type="user",
            resource_id=created_user.id if created_user else None,
        )
    db.commit()
    return render_template(request, "users/bulk_result.html", ctx=ctx, results=results, pending=[])
