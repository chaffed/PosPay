# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pospay.auth.deps import require_permission
from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.domain.check_image import OcrStatus
from pospay.networks.check.ocr_processing import create_check_image, process_check_image_ocr
from pospay.repositories.check_image_repo import CheckImageRepository
from pospay.schemas.check_image import CheckImageRead
from pospay.services import audit_log_service

router = APIRouter(prefix="/check-images", tags=["check-images"])


def _run_ocr_in_background(engine: Engine, check_image_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    # Opens its own Session (not the request's, which is closed by the time this runs)
    # bound to the same engine the request used — bind is threaded through explicitly
    # rather than via the global get_session_factory() so this respects test overrides
    # of get_db, instead of silently writing to whatever DATABASE_URL is globally cached.
    # tenant_id is passed to process_check_image_ocr so it can set Postgres RLS's session
    # variable itself (and re-set it after its internal commit — see that function).
    session = Session(bind=engine)
    try:
        process_check_image_ocr(session, check_image_id, tenant_id=tenant_id)
    finally:
        session.close()


@router.post("", response_model=CheckImageRead, status_code=status.HTTP_201_CREATED)
def upload_check_image(
    background_tasks: BackgroundTasks,
    front_image: UploadFile = File(...),
    back_image: UploadFile | None = File(None),
    paid_item_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("check_image:write")),
) -> CheckImageRead:
    front_bytes = front_image.file.read()
    back_bytes = back_image.file.read() if back_image is not None else None

    check_image = create_check_image(
        db, ctx.tenant_id, front_bytes=front_bytes, back_bytes=back_bytes, paid_item_id=paid_item_id
    )
    audit_log_service.record_action(
        db,
        ctx.tenant_id,
        actor_user_id=ctx.user_id,
        channel="api",
        action="check_image.upload",
        summary="Uploaded a check image",
        resource_type="check_image",
        resource_id=check_image.id,
    )
    db.commit()

    background_tasks.add_task(_run_ocr_in_background, db.get_bind(), check_image.id, ctx.tenant_id)
    return CheckImageRead.model_validate(check_image)


@router.get("/{check_image_id}", response_model=CheckImageRead)
def get_check_image(
    check_image_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("check_image:read")),
) -> CheckImageRead:
    check_image = CheckImageRepository(db, ctx.tenant_id).get(check_image_id)
    if check_image is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Check image not found")
    return CheckImageRead.model_validate(check_image)


@router.post("/{check_image_id}/reprocess", response_model=CheckImageRead)
def reprocess_check_image(
    check_image_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_permission("check_image:write")),
) -> CheckImageRead:
    check_image = CheckImageRepository(db, ctx.tenant_id).get(check_image_id)
    if check_image is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Check image not found")

    check_image.ocr_status = OcrStatus.PENDING
    audit_log_service.record_action(
        db,
        ctx.tenant_id,
        actor_user_id=ctx.user_id,
        channel="api",
        action="check_image.reprocess",
        summary="Requested OCR reprocessing of a check image",
        resource_type="check_image",
        resource_id=check_image.id,
    )
    db.commit()

    background_tasks.add_task(_run_ocr_in_background, db.get_bind(), check_image.id, ctx.tenant_id)
    return CheckImageRead.model_validate(check_image)
