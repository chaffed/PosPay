from pathlib import Path

from fastapi.templating import Jinja2Templates

from pospay.db.tenancy import TenantContext

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


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
