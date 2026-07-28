# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Request, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from pospay.api.v1.router import api_router
from pospay.config import get_settings
from pospay.web.deps import WebAuthRequired, WebForbidden, WebNotFound, render_template
from pospay.web.router import web_router

_STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def _lifespan(app: FastAPI):
    scheduler = None
    if get_settings().enable_ml_scheduler:
        from pospay.workers.scheduler import start_scheduler, stop_scheduler

        scheduler = start_scheduler()
    yield
    if scheduler is not None:
        stop_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(title="PosPay", version="0.1.0", lifespan=_lifespan)

    # Importing each network package triggers its register_adapter() call at import
    # time (see networks/registry.py). Adding a new network later means adding one
    # import here plus its own package — nothing else in this file changes.
    import pospay.networks.check  # noqa: F401
    import pospay.networks.ach  # noqa: F401

    app.include_router(api_router)
    app.include_router(web_router)
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
