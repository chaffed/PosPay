import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from pospay.db.base import Base, new_uuid


class PaidItemMatchStatus(str, enum.Enum):
    PENDING = "pending"  # created, matching not yet run (should be transient)
    MATCHED = "matched"
    EXCEPTION = "exception"


class PaidItemSettlementStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    RETURNED = "returned"


class PaidItemSource(str, enum.Enum):
    API = "api"
    BULK_FILE = "bulk_file"
    MANUAL = "manual"


class PaidItem(Base):
    """A presented check clearing through the bank — the item positive pay matches
    against the issued-item file. This is the 'source item' pointed to by exception_item
    (network_code='check') when matching fails."""

    __tablename__ = "paid_item"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("account.id"), nullable=False, index=True)

    check_number: Mapped[str] = mapped_column(String(32), nullable=False)
    presented_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    presented_date: Mapped[date] = mapped_column(Date, nullable=False)

    matched_issued_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("issued_item.id"), nullable=True)
    match_status: Mapped[PaidItemMatchStatus] = mapped_column(
        Enum(PaidItemMatchStatus, name="paid_item_match_status", native_enum=False, length=20),
        nullable=False,
        default=PaidItemMatchStatus.PENDING,
    )
    settlement_status: Mapped[PaidItemSettlementStatus] = mapped_column(
        Enum(PaidItemSettlementStatus, name="paid_item_settlement_status", native_enum=False, length=20),
        nullable=False,
        default=PaidItemSettlementStatus.PENDING,
    )
    source: Mapped[PaidItemSource] = mapped_column(
        Enum(PaidItemSource, name="paid_item_source", native_enum=False, length=20), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
