import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from pospay.db.base import Base, new_uuid


class ExceptionStatus(str, enum.Enum):
    OPEN = "open"
    PENDING_APPROVAL = "pending_approval"  # maker recommendation submitted, awaiting checker
    PAY = "pay"
    RETURN = "return"
    ESCALATED = "escalated"


class ExceptionItem(Base):
    """Network-agnostic. One row per transaction that failed a network's matching rules.
    `source_item_id` is a generic pointer (no DB-level FK) resolved via
    networks.registry.get_adapter(network_code).load_source_item() — see networks/base.py
    for why: a typed FK column per network doesn't scale past a couple of networks."""

    __tablename__ = "exception_item"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), nullable=False, index=True)
    network_code: Mapped[str] = mapped_column(ForeignKey("payment_network.code"), nullable=False, index=True)

    source_item_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    related_reference_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    exception_types: Mapped[str] = mapped_column(String(500), nullable=False)  # comma-separated ExceptionType values
    status: Mapped[ExceptionStatus] = mapped_column(
        Enum(ExceptionStatus, name="exception_status", native_enum=False, length=20),
        nullable=False,
        default=ExceptionStatus.OPEN,
    )

    ml_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ml_model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Holds a maker's proposed outcome while awaiting a checker's approval (dual-control
    # tenants only). Cleared into a real Decision row once decide() finalizes it — these
    # columns are working state, not the ground-truth ML training signal Decision is.
    recommended_outcome: Mapped[str | None] = mapped_column(String(10), nullable=True)
    recommended_reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recommended_notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    recommended_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"), nullable=True)

    decision_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
