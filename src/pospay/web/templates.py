from pathlib import Path

from fastapi.templating import Jinja2Templates

from pospay.auth.rbac import role_has_permission
from pospay.domain.user import UserRole

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _can(role: str | None, permission: str) -> bool:
    """Exposed to every template as `can(ctx.role, "resource:action")` — the exact same
    permission matrix the server-side route dependencies check (auth/rbac.py), so a
    template can never show a control that the corresponding POST route would reject.
    This is cosmetic only: hiding a button doesn't grant anything, the route's own
    require_web_permission()/require_permission() dependency is what actually enforces it."""
    if role is None:
        return False
    return role_has_permission(UserRole(role), permission)


templates.env.globals["can"] = _can
