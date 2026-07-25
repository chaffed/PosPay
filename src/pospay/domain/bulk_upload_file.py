import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from pospay.db.base import Base, new_uuid


class BulkUploadKind(str, enum.Enum):
    ISSUED_ITEMS = "issued_items"
    ACH_TRANSACTIONS = "ach_transactions"
    USERS = "users"


class BulkUploadFile(Base):
    """The original bytes of every bulk file a user submits (issued items, ACH, users —
    see services/bulk_upload_file_service.py), kept for audit purposes even when the file
    is rejected outright: a malformed submission is still evidence of what was actually
    sent. `sha256_hex` is a plain content fingerprint anyone can quote independently;
    `hmac_signature_hex` is the actual tamper-evidence, computed with a server-held secret
    (bulk_import/signing.py) — re-verified against the file on disk on demand, not just
    trusted as a stored flag."""

    __tablename__ = "bulk_upload_file"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), nullable=False, index=True)
    kind: Mapped[BulkUploadKind] = mapped_column(Enum(BulkUploadKind, name="bulk_upload_kind", native_enum=False, length=20), nullable=False)

    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256_hex: Mapped[str] = mapped_column(String(64), nullable=False)
    hmac_signature_hex: Mapped[str] = mapped_column(String(64), nullable=False)

    succeeded_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
