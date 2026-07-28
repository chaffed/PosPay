# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from pathlib import Path

from fastapi.templating import Jinja2Templates

from pospay.db.tenancy import TenantContext

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_STATIC_DIR = Path(__file__).parent.parent / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _asset_version(relative_path: str) -> int:
    """Exposed to every template as `asset_version("js/app.js")` — a cache-busting query
    param derived from the static file's own mtime, appended to its URL in base.html.
    Without this, a browser can keep serving a stale cached copy of app.js/app.css after
    a deploy (StaticFiles' response carries only Last-Modified/ETag, no Cache-Control, so
    heuristic caching can serve an old copy without even a revalidation request) — the
    query string changes automatically whenever the underlying file's mtime changes, no
    manual version bump required."""
    try:
        return int((_STATIC_DIR / relative_path).stat().st_mtime)
    except OSError:
        return 0


templates.env.globals["asset_version"] = _asset_version


def _can(ctx: TenantContext | None, permission: str) -> bool:
    """Exposed to every template as `can(ctx, "resource:action")` — checks the exact same
    ctx.permissions set the server-side route dependencies check
    (web/deps.py::require_web_permission), so a template can never show a control that
    the corresponding POST route would reject. This is cosmetic only: hiding a button
    doesn't grant anything, the route's own require_web_permission()/require_permission()
    dependency is what actually enforces it."""
    if ctx is None:
        return False
    return permission in ctx.permissions


templates.env.globals["can"] = _can
