# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from pathlib import Path
from urllib.parse import urlencode

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


def _format_metrics(metrics: dict | None) -> str:
    """Exposed to every template as `format_metrics(m.metrics_json)` — renders an ML
    model's metrics dict (precision/recall/auc from ml/train.py, or {"error": ...} for a
    failed retrain from workers/tasks.py::_train_and_log) as a readable string instead of
    a raw Python dict repr (`{'precision': 0.5, ...}`)."""
    if not metrics:
        return "—"
    parts = []
    for key, value in metrics.items():
        if key in ("precision", "recall") and isinstance(value, (int, float)):
            parts.append(f"{key.capitalize()}: {value * 100:.0f}%")
        elif isinstance(value, (int, float)):
            parts.append(f"{key.upper() if key == 'auc' else key.capitalize()}: {value:.2f}")
        else:
            parts.append(f"{key.capitalize()}: {value}")
    return ", ".join(parts)


templates.env.globals["format_metrics"] = _format_metrics


def _currency(value):
    """Registered as the `currency` Jinja filter — formats a Decimal/numeric amount as
    `$1,234.56`. Returns None unchanged (rather than raising or printing "None") so
    existing `{{ x or "any" }}` fallbacks — e.g. stop_payments/list.html's nullable stop
    amount — keep working exactly as before."""
    if value is None:
        return None
    return f"${value:,.2f}"


templates.env.filters["currency"] = _currency


def _pager_href(request, page: int) -> str:
    """Exposed to templates as `pager_href(request, page)` — used by
    templates/_macros/pagination.html's Prev/Next links. Builds a query string with
    `page` replaced (or added), preserving every other query param already on the
    request (status filters, network filters, etc.) so paging never resets a filter."""
    params = dict(request.query_params)
    params["page"] = str(page)
    return "?" + urlencode(params)


templates.env.globals["pager_href"] = _pager_href
