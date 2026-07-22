from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from pospay.db.tenancy import TenantContext
from pospay.web.deps import get_web_context, render_template

router = APIRouter(prefix="/ui", tags=["web-dashboard"])


@router.get("/")
def dashboard(request: Request, ctx: TenantContext = Depends(get_web_context)) -> HTMLResponse:
    return render_template(request, "dashboard.html", ctx=ctx)
