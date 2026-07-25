import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from pospay.bulk_import.file_storage import read_uploaded_file
from pospay.db.session import get_db
from pospay.db.tenancy import TenantContext
from pospay.domain.bulk_upload_file import BulkUploadFile, BulkUploadKind
from pospay.services import bulk_upload_file_service
from pospay.web.deps import WebForbidden, WebNotFound, get_web_context, render_template

router = APIRouter(prefix="/ui/bulk-uploads", tags=["web-bulk-uploads"])

# One route serves all three upload kinds, so the permission to check is looked up per
# record rather than fixed at the dependency level — the same permission that gated the
# original upload gates viewing/downloading it later.
_PERMISSION_BY_KIND = {
    BulkUploadKind.ISSUED_ITEMS: "issued_item:write",
    BulkUploadKind.ACH_TRANSACTIONS: "ach_transaction:write",
    BulkUploadKind.USERS: "user:manage",
}


def _get_authorized_record(db: Session, ctx: TenantContext, upload_id: uuid.UUID) -> BulkUploadFile:
    record = bulk_upload_file_service.get_uploaded_file(db, ctx.tenant_id, upload_id)
    if record is None:
        raise WebNotFound()
    if _PERMISSION_BY_KIND[record.kind] not in ctx.permissions:
        raise WebForbidden()
    return record


@router.get("/{upload_id}")
def bulk_upload_detail(
    request: Request, upload_id: uuid.UUID, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_web_context)
) -> HTMLResponse:
    record = _get_authorized_record(db, ctx, upload_id)
    # Recomputed live on every render — a stale "verified" flag stored at upload time
    # would defeat the entire point, which is detecting a change made SINCE then.
    verified = bulk_upload_file_service.verify_uploaded_file(db, ctx.tenant_id, upload_id)
    return render_template(request, "bulk_uploads/detail.html", ctx=ctx, record=record, verified=verified)


@router.get("/{upload_id}/download")
def bulk_upload_download(
    upload_id: uuid.UUID, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_web_context)
) -> Response:
    record = _get_authorized_record(db, ctx, upload_id)
    data = read_uploaded_file(record.storage_path)
    encoded_name = quote(record.original_filename)
    return Response(
        content=data,
        media_type=record.content_type or "application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename=\"upload\"; filename*=UTF-8''{encoded_name}"},
    )
