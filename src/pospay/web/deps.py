import jwt
from fastapi import Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from pospay.auth.deps import AccessRevoked, WrongTokenType, decode_and_build_context
from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.web.security import (
    ACCESS_COOKIE_NAME,
    MFA_COOKIE_NAME,
    read_or_generate_csrf_token,
    set_csrf_cookie_if_new,
)
from pospay.web.templates import templates


class WebAuthRequired(Exception):
    """Raised instead of a JSON 401 anywhere in /ui/* — a browser needs a redirect to the
    login page, not a JSON error body. Caught by an exception handler registered in
    main.py that returns a RedirectResponse. `next_path` round-trips through the login
    form so a successful login can send the user back where they were headed."""

    def __init__(self, next_path: str | None = None):
        self.next_path = next_path


class WebForbidden(Exception):
    """Raised when a role lacks a permission for a /ui/* route — rendered as an HTML
    error page (not a JSON 403) by an exception handler in main.py."""


class WebNotFound(Exception):
    """Raised when a /ui/* route's resource id doesn't resolve to a row this tenant owns
    (either truly missing, or belonging to another tenant — same outward response either
    way, so this never leaks which). Rendered as an HTML 404 page in main.py."""


def get_web_context(request: Request, db: Session = Depends(get_db)) -> TenantContext:
    token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not token:
        raise WebAuthRequired(next_path=request.url.path)
    try:
        return decode_and_build_context(token, db, expected_type="access")
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, WrongTokenType, AccessRevoked):
        # Phase 1: any failure (including plain expiry, or an access/membership that was
        # deactivated since the token was issued) sends the user back to login.
        raise WebAuthRequired(next_path=request.url.path) from None


def get_mfa_pending_web_context(request: Request, db: Session = Depends(get_db)) -> TenantContext:
    """For /ui/login/webauthn/* only — mirrors auth.get_mfa_pending_context but reads the
    mfa_token cookie instead of an Authorization header (see web/security.py)."""
    token = request.cookies.get(MFA_COOKIE_NAME)
    if not token:
        raise WebAuthRequired(next_path="/ui/login")
    try:
        return decode_and_build_context(token, db, expected_type="mfa_pending")
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, WrongTokenType, AccessRevoked):
        raise WebAuthRequired(next_path="/ui/login") from None


def require_web_permission(permission: str):
    def _check(ctx: TenantContext = Depends(get_web_context)) -> TenantContext:
        if permission not in ctx.permissions:
            raise WebForbidden()
        return ctx

    return _check


def render_template(
    request: Request,
    name: str,
    *,
    ctx: TenantContext | None = None,
    status_code: int = 200,
    **extra,
) -> HTMLResponse:
    """Every /ui/* route renders through this so `request`, `ctx` (base.html's role-aware
    nav), and `csrf_token` (base.html's logout form, and any page-specific form) are never
    forgotten — the one thing every template needs, regardless of what page-specific data
    it also needs."""
    csrf_token = read_or_generate_csrf_token(request)
    context = {"ctx": ctx, "csrf_token": csrf_token, **extra}
    response = templates.TemplateResponse(request, name, context, status_code=status_code)
    set_csrf_cookie_if_new(request, response, csrf_token)
    return response
