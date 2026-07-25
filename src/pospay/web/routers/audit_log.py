from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.repositories.user_repo import UserRepository
from pospay.services import audit_log_service
from pospay.web.deps import render_template, require_web_permission

router = APIRouter(prefix="/ui/audit-log", tags=["web-audit-log"])


def _rows_newest_first(db: Session, tenant_id) -> list[dict]:
    entries = audit_log_service.list_entries(db, tenant_id)
    user_repo = UserRepository(db)
    rows = []
    for entry in reversed(entries):
        actor = user_repo.get(entry.actor_user_id) if entry.actor_user_id else None
        rows.append({"entry": entry, "actor_email": actor.email if actor else "(system)"})
    return rows


@router.get("")
def list_audit_log(
    request: Request, db: Session = Depends(get_db), ctx: TenantContext = Depends(require_web_permission("audit_log:read"))
) -> HTMLResponse:
    return render_template(request, "audit_log/list.html", ctx=ctx, rows=_rows_newest_first(db, ctx.tenant_id))


@router.get("/verify")
def verify_audit_log(
    request: Request, db: Session = Depends(get_db), ctx: TenantContext = Depends(require_web_permission("audit_log:read"))
) -> HTMLResponse:
    result = audit_log_service.verify_chain(db, ctx.tenant_id)
    return render_template(
        request, "audit_log/list.html", ctx=ctx, rows=_rows_newest_first(db, ctx.tenant_id), verification=result
    )
