import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.domain.check_image import OcrStatus
from pospay.networks.check.ocr_processing import create_check_image, process_check_image_ocr
from pospay.repositories.check_image_repo import CheckImageRepository
from pospay.repositories.paid_item_repo import PaidItemRepository
from pospay.web.deps import WebNotFound, get_web_context, render_template, require_web_permission
from pospay.web.security import verify_csrf

router = APIRouter(prefix="/ui/check-images", tags=["web-check-images"])


def _run_ocr_in_background(engine: Engine, check_image_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    # Same pattern as api/v1/check_images.py: a fresh Session bound to the request's
    # engine (not the global session factory), so this respects test overrides and
    # Postgres RLS's tenant-scoped session variable — see that file for the full rationale.
    session = Session(bind=engine)
    try:
        process_check_image_ocr(session, check_image_id, tenant_id=tenant_id)
    finally:
        session.close()


@router.get("")
def list_check_images(
    request: Request, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_web_context)
) -> HTMLResponse:
    images = CheckImageRepository(db, ctx.tenant_id).list()
    return render_template(request, "check_images/list.html", ctx=ctx, images=images)


@router.get("/upload")
def upload_form(
    request: Request,
    paid_item_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("paid_item:write")),
) -> HTMLResponse:
    paid_items = PaidItemRepository(db, ctx.tenant_id).list()
    return render_template(request, "check_images/upload.html", ctx=ctx, paid_items=paid_items, selected_paid_item_id=paid_item_id)


@router.post("")
def upload_check_image(
    background_tasks: BackgroundTasks,
    front_image: UploadFile = File(...),
    paid_item_id: str = "",
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("paid_item:write")),
    _csrf: None = Depends(verify_csrf),
) -> RedirectResponse:
    front_bytes = front_image.file.read()
    parsed_paid_item_id = uuid.UUID(paid_item_id) if paid_item_id else None

    check_image = create_check_image(db, ctx.tenant_id, front_bytes=front_bytes, back_bytes=None, paid_item_id=parsed_paid_item_id)
    db.commit()

    background_tasks.add_task(_run_ocr_in_background, db.get_bind(), check_image.id, ctx.tenant_id)
    return RedirectResponse(f"/ui/check-images/{check_image.id}?flash=Uploaded.+OCR+is+processing.", status_code=303)


@router.get("/{check_image_id}")
def check_image_detail(
    request: Request,
    check_image_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_web_context),
) -> HTMLResponse:
    image = CheckImageRepository(db, ctx.tenant_id).get(check_image_id)
    if image is None:
        raise WebNotFound()
    return render_template(request, "check_images/detail.html", ctx=ctx, image=image)


@router.post("/{check_image_id}/reprocess")
def reprocess_check_image(
    check_image_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_web_permission("paid_item:write")),
    _csrf: None = Depends(verify_csrf),
) -> RedirectResponse:
    image = CheckImageRepository(db, ctx.tenant_id).get(check_image_id)
    if image is None:
        raise WebNotFound()
    image.ocr_status = OcrStatus.PENDING
    db.commit()
    background_tasks.add_task(_run_ocr_in_background, db.get_bind(), image.id, ctx.tenant_id)
    return RedirectResponse(f"/ui/check-images/{check_image_id}?flash=Reprocessing.", status_code=303)
