import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
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
from pospay.domain.user import User
from pospay.schemas.webauthn import RegistrationVerifyRequest
from pospay.web.deps import get_web_context, render_template
from pospay.web.security import verify_csrf, verify_csrf_header

router = APIRouter(prefix="/ui/security", tags=["web-security-settings"])


@router.get("")
def security_settings(
    request: Request,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_web_context),
) -> HTMLResponse:
    credentials = list_credentials(db, ctx.tenant_id, ctx.user_id)
    return render_template(request, "security/webauthn.html", ctx=ctx, credentials=credentials)


@router.post("/webauthn/register/options")
def register_options(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_web_context),
    _csrf: None = Depends(verify_csrf_header),
) -> Response:
    user = db.get(User, ctx.user_id)
    options_json = begin_registration(db, user)
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
        credential = complete_registration(db, user, payload.credential, nickname=payload.nickname)
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
