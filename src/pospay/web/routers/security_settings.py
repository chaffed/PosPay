# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from pospay.auth.webauthn_service import (
    WebauthnError,
    begin_registration,
    complete_registration,
    delete_credential,
    list_credentials,
)
from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.domain.notification import NotificationType
from pospay.domain.user import User
from pospay.schemas.webauthn import RegistrationVerifyRequest
from pospay.services import notification_service
from pospay.web.deps import get_web_context, render_template
from pospay.web.security import verify_csrf, verify_csrf_header

router = APIRouter(prefix="/ui/security", tags=["web-security-settings"])

# ACCOUNT_LOCKED's email is not preference-controlled (services/notification_service.py's
# _ALWAYS_EMAIL_TYPES) -- excluded here entirely rather than rendered as a disabled,
# always-checked control, since there's nothing for the user to meaningfully see or do
# with it.
_PREFERENCE_TYPES = [t for t in NotificationType if t != NotificationType.ACCOUNT_LOCKED]

_NOTIFICATION_TYPE_LABELS = {
    NotificationType.EXCEPTION_CREATED: "New exception ready for review",
    NotificationType.RECOMMENDATION_AWAITING_APPROVAL: "A recommendation is awaiting your approval",
    NotificationType.ACCOUNT_UNLOCKED: "Your account was unlocked",
    NotificationType.EXCEPTION_AUTO_DECIDED: "An exception was auto-decided",
}


@router.get("")
def security_settings(
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_web_context),
) -> HTMLResponse:
    credentials = list_credentials(db, ctx.tenant_id, ctx.user_id)
    return render_template(request, "security/webauthn.html", ctx=ctx, credentials=credentials)


@router.get("/notifications")
def notification_settings(
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_web_context),
) -> HTMLResponse:
    user = db.get(User, ctx.user_id)
    preferences = notification_service.get_preferences(db, ctx.user_id)
    rows = [
        {
            "type": t,
            "label": _NOTIFICATION_TYPE_LABELS[t],
            "email_enabled": preferences[t].email_enabled if t in preferences else True,
            "sms_enabled": preferences[t].sms_enabled if t in preferences else False,
        }
        for t in _PREFERENCE_TYPES
    ]
    return render_template(request, "security/notifications.html", ctx=ctx, phone=user.phone, rows=rows)


@router.post("/notifications/phone")
def update_phone(
    request: Request,
    phone: str = Form(""),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_web_context),
    _csrf: None = Depends(verify_csrf),
) -> RedirectResponse:
    user = db.get(User, ctx.user_id)
    notification_service.set_phone(db, user, phone.strip() or None)
    db.commit()
    return RedirectResponse("/ui/security/notifications", status_code=303)


@router.post("/notifications")
async def update_notification_preferences(
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_web_context),
    _csrf: None = Depends(verify_csrf),
) -> RedirectResponse:
    form = await request.form()
    for notification_type in _PREFERENCE_TYPES:
        notification_service.set_preference(
            db, ctx.user_id, notification_type,
            email_enabled=f"email_{notification_type.value}" in form,
            sms_enabled=f"sms_{notification_type.value}" in form,
        )
    db.commit()
    return RedirectResponse("/ui/security/notifications", status_code=303)


@router.post("/webauthn/register/options")
def register_options(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_web_context),
    _csrf: None = Depends(verify_csrf_header),
) -> Response:
    user = db.get(User, ctx.user_id)
    options_json = begin_registration(db, user, ctx.tenant_id)
    db.commit()
    return Response(content=options_json, media_type="application/json")


@router.post("/webauthn/register/verify")
def register_verify(
    payload: RegistrationVerifyRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_web_context),
    _csrf: None = Depends(verify_csrf_header),
) -> JSONResponse:
    user = db.get(User, ctx.user_id)
    try:
        credential = complete_registration(db, user, ctx.tenant_id, payload.credential, nickname=payload.nickname)
    except WebauthnError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    db.commit()
    return JSONResponse({"id": str(credential.id), "nickname": credential.nickname})


@router.post("/webauthn/{credential_id}/delete")
def delete_credential_route(
    credential_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_web_context),
    _csrf: None = Depends(verify_csrf),
) -> RedirectResponse:
    deleted = delete_credential(db, ctx.tenant_id, ctx.user_id, credential_id)
    db.commit()
    flash = "Security key removed." if deleted else "Security key not found."
    return RedirectResponse(f"/ui/security?flash={quote(flash)}", status_code=303)
