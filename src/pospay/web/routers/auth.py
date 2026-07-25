from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from pospay.auth.login_service import authenticate_password
from pospay.auth.security import create_token
from pospay.auth.webauthn_service import WebauthnError, begin_authentication, complete_authentication
from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.domain.user import User
from pospay.schemas.webauthn import AuthenticationVerifyRequest
from pospay.services.tenant_service import get_tenant_branding_by_slug
from pospay.web.deps import get_mfa_pending_web_context, render_template
from pospay.web.security import (
    clear_auth_cookies,
    clear_mfa_cookie,
    safe_next_path,
    set_access_cookie,
    set_mfa_cookie,
    set_refresh_cookie,
    verify_csrf,
    verify_csrf_header,
)

router = APIRouter(prefix="/ui", tags=["web-auth"])


@router.get("/login")
def login_form(request: Request, next: str | None = None) -> HTMLResponse:
    return render_template(request, "auth/login.html", next_path=safe_next_path(next))


@router.post("/login")
def login_submit(
    request: Request,
    tenant_slug: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/ui/"),
    db: Session = Depends(get_db),
    _csrf: None = Depends(verify_csrf),
) -> HTMLResponse:
    next_path = safe_next_path(next)
    identity = authenticate_password(db, tenant_slug, email, password)
    if identity is None:
        # Best-effort branding lookup by the submitted slug, purely cosmetic — a login
        # link that arrived branded (via /ui/login/{slug}) stays branded through a failed
        # attempt instead of dropping back to the generic form. Never used for the actual
        # auth decision above, which already collapsed every failure reason into one.
        return render_template(
            request,
            "auth/login.html",
            status_code=401,
            error="Invalid organization slug, email, or password.",
            tenant_slug=tenant_slug,
            email=email,
            next_path=next_path,
            branding=get_tenant_branding_by_slug(db, tenant_slug),
        )

    user, tenant, membership = identity.user, identity.tenant, identity.membership

    if identity.mfa_required:
        mfa_token = create_token(
            user_id=user.id, tenant_id=tenant.id, security_group_id=membership.security_group_id, token_type="mfa_pending"
        )
        response = RedirectResponse(f"/ui/login/webauthn?next={quote(next_path)}", status_code=303)
        set_mfa_cookie(response, mfa_token)
        return response

    access_token = create_token(
        user_id=user.id, tenant_id=tenant.id, security_group_id=membership.security_group_id, token_type="access"
    )
    refresh_token = create_token(
        user_id=user.id, tenant_id=tenant.id, security_group_id=membership.security_group_id, token_type="refresh"
    )
    response = RedirectResponse(next_path, status_code=303)
    set_access_cookie(response, access_token)
    set_refresh_cookie(response, refresh_token)
    return response


@router.post("/logout")
def logout(_csrf: None = Depends(verify_csrf)) -> RedirectResponse:
    # Deliberately does not require get_web_context — a user with an already-expired or
    # garbled token must still be able to clear cookies and get back to a working login
    # page, not get stuck in a redirect loop.
    response = RedirectResponse("/ui/login", status_code=303)
    clear_auth_cookies(response)
    return response


# --- WebAuthn second factor (login-time) ---
#
# The mfa_token cookie set above is HttpOnly and scoped to this path — the browser JS
# below (static/js/webauthn.js) never sees it or any other token; it only ever handles
# the WebAuthn options/credential JSON blobs. Both routes call auth/webauthn_service.py
# directly (in-process), not the JSON API — see the architecture plan for why.


@router.get("/login/webauthn")
def login_webauthn_page(request: Request, next: str | None = None) -> HTMLResponse:
    return render_template(request, "auth/login_webauthn.html", next_path=safe_next_path(next))


@router.post("/login/webauthn/options")
def login_webauthn_options(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_mfa_pending_web_context),
    _csrf: None = Depends(verify_csrf_header),
) -> Response:
    user = db.get(User, ctx.user_id)
    try:
        options_json = begin_authentication(db, user, ctx.tenant_id)
    except WebauthnError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    db.commit()
    return Response(content=options_json, media_type="application/json")


@router.post("/login/webauthn/verify")
def login_webauthn_verify(
    payload: AuthenticationVerifyRequest,
    next: str = "/ui/",
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_mfa_pending_web_context),
    _csrf: None = Depends(verify_csrf_header),
) -> JSONResponse:
    user = db.get(User, ctx.user_id)
    try:
        complete_authentication(db, user, ctx.tenant_id, payload.credential)
    except WebauthnError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    db.commit()

    next_path = safe_next_path(next)
    response = JSONResponse({"redirect": next_path})
    access_token = create_token(
        user_id=user.id, tenant_id=ctx.tenant_id, security_group_id=ctx.security_group_id, token_type="access"
    )
    refresh_token = create_token(
        user_id=user.id, tenant_id=ctx.tenant_id, security_group_id=ctx.security_group_id, token_type="refresh"
    )
    set_access_cookie(response, access_token)
    set_refresh_cookie(response, refresh_token)
    clear_mfa_cookie(response)
    return response


# NOTE: /login/{tenant_slug} must be registered LAST (after every literal /login/*
# route above, in particular /login/webauthn*) — FastAPI matches path patterns in
# registration order, and "webauthn" would otherwise be captured as tenant_slug and
# rejected/mismatched (a nonexistent tenant, silently falling back to unbranded) before
# the real /login/webauthn route is ever tried. Same class of pitfall as /bulk vs
# /{item_id} elsewhere in this codebase.


@router.get("/login/{tenant_slug}")
def branded_login_form(request: Request, tenant_slug: str, next: str | None = None, db: Session = Depends(get_db)) -> HTMLResponse:
    """A bookmarkable/shareable branded login link for one organization
    (services/tenant_service.py::get_tenant_branding_by_slug). An unknown or inactive
    slug falls back to the plain generic form rather than a 404 — same
    don't-reveal-which-part-was-wrong posture as authenticate_password."""
    return render_template(
        request,
        "auth/login.html",
        next_path=safe_next_path(next),
        tenant_slug=tenant_slug,
        branding=get_tenant_branding_by_slug(db, tenant_slug),
    )
