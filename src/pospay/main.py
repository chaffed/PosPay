# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Request, status
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from pospay.api.v1.router import api_router
from pospay.config import assert_production_safe, get_settings
from pospay.web.client_ip import get_client_ip
from pospay.web.deps import WebAuthRequired, WebForbidden, WebNotFound, render_template
from pospay.web.rate_limit import limiter
from pospay.web.router import web_router
from pospay.web.security_headers import apply_security_headers, new_csp_nonce

_STATIC_DIR = Path(__file__).parent / "static"
_DOCS_SCREENSHOTS_DIR = Path(__file__).parent.parent.parent / "docs" / "screenshots"
logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    scheduler = None
    settings = get_settings()
    if settings.enable_ml_scheduler or settings.auto_import_enabled or settings.notifications_enabled or settings.enable_disposition_scheduler:
        from pospay.workers.scheduler import start_scheduler, stop_scheduler

        scheduler = start_scheduler()

    if settings.demo_tenant_enabled:
        # Idempotent -- a safe no-op on every restart after the first. Best-effort: a
        # seeding failure (e.g. the DB isn't migrated yet) must never prevent the app
        # itself from starting.
        from pospay.db.session import get_session_factory
        from pospay.services.demo_tenant_service import DemoTenantNotConfigured, ensure_demo_tenant

        session = get_session_factory()()
        try:
            ensure_demo_tenant(session)
        except DemoTenantNotConfigured as exc:
            logger.warning("Demo tenant not provisioned at startup: %s", exc)
        except Exception:  # noqa: BLE001 -- seeding failure must never block app startup
            logger.exception("Failed to ensure the demo tenant exists at startup")
            session.rollback()
        finally:
            session.close()

    yield
    if scheduler is not None:
        stop_scheduler()


def create_app() -> FastAPI:
    # First thing, before anything else — a production deployment still pointing at
    # the checked-in dev/test signing keys or the default SSO encryption key must never
    # even finish starting (see SECURITY_REVIEW.md and config.py::assert_production_safe).
    assert_production_safe(get_settings())

    app = FastAPI(title="PosPay", version="1.0.0", lifespan=_lifespan)

    # Importing each network package triggers its register_adapter() call at import
    # time (see networks/registry.py). Adding a new network later means adding one
    # import here plus its own package — nothing else in this file changes.
    import pospay.networks.check  # noqa: F401
    import pospay.networks.ach  # noqa: F401

    @app.middleware("http")
    async def _limit_request_body_size(request: Request, call_next):
        # Fast, uniform first line of defense against oversized uploads — reads
        # Content-Length off every incoming request before any route handler (or
        # per-parser code) ever sees the body. Doesn't catch a chunked-transfer-encoded
        # request omitting Content-Length; not adding a full streaming body-size
        # enforcer for that, same proportionality call as elsewhere in this pass — see
        # SECURITY_REVIEW.md.
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = None
            if declared_size is not None and declared_size > get_settings().max_request_body_bytes:
                return PlainTextResponse("Request body too large", status_code=status.HTTP_413_CONTENT_TOO_LARGE)
        return await call_next(request)

    @app.middleware("http")
    async def _rate_limit_global(request: Request, call_next):
        # A blanket per-IP safety net across every route -- see web/rate_limit.py for the
        # in-memory sliding-window design and web/client_ip.py for how the IP itself is
        # resolved (direct connection by default; trusts X-Forwarded-For only if
        # POSPAY_TRUSTED_PROXY_COUNT says a reverse proxy/WAF is actually in front of
        # this). Individual routes (e.g. /ui/markdown-preview) can layer a stricter limit
        # of their own on top via web.rate_limit.rate_limit(), tracked as a separate
        # bucket under the same client key.
        client_ip = get_client_ip(request) or "unknown"
        if not limiter.allow(client_ip, "global", limit=get_settings().rate_limit_per_minute, window_seconds=60.0):
            return PlainTextResponse("Too many requests -- please slow down.", status_code=status.HTTP_429_TOO_MANY_REQUESTS)
        return await call_next(request)

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        # Registered last, deliberately: Starlette's middleware stack wraps in reverse
        # registration order, so the last one registered here is outermost -- it sets
        # request.state.csp_nonce before either middleware above (or the route handler)
        # ever runs, so a template rendered deep inside can always find it, and it gets
        # to add headers to whatever response comes back out -- a normal page, a 429 from
        # the rate limiter above, a 413 from the body-size guard, or an exception-handler
        # response -- not just the happy path.
        request.state.csp_nonce = new_csp_nonce()
        response = await call_next(request)
        apply_security_headers(request, response)
        return response

    app.include_router(api_router)
    app.include_router(web_router)
    # Registered before the broader "/static" mount below -- Starlette matches mounts by
    # prefix in registration order, so the more specific path must come first or every
    # request under it would be swallowed by "/static" (and 404, since that directory has
    # no "docs-screenshots" subfolder of its own).
    app.mount(
        "/static/docs-screenshots",
        StaticFiles(directory=str(_DOCS_SCREENSHOTS_DIR), check_dir=False),
        name="docs_screenshots",
    )
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.exception_handler(WebAuthRequired)
    def _handle_web_auth_required(request: Request, exc: WebAuthRequired) -> RedirectResponse:
        from pospay.web.security import safe_next_path

        next_path = safe_next_path(exc.next_path)
        url = "/ui/login" if next_path == "/ui/" else f"/ui/login?next={quote(next_path)}"
        return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)

    @app.exception_handler(WebForbidden)
    def _handle_web_forbidden(request: Request, exc: WebForbidden):
        return render_template(
            request,
            "error.html",
            status_code=status.HTTP_403_FORBIDDEN,
            status_code_display=403,
            message="You don't have permission to do that.",
        )

    @app.exception_handler(WebNotFound)
    def _handle_web_not_found(request: Request, exc: WebNotFound):
        return render_template(
            request,
            "error.html",
            status_code=status.HTTP_404_NOT_FOUND,
            status_code_display=404,
            message="That item couldn't be found.",
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
