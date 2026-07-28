# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from pospay.db.base import Base, new_uuid


class DecisionOutcome(str, enum.Enum):
    PAY = "pay"
    RETURN = "return"


class Decision(Base):
    """The human pay/return decision on an exception — network-agnostic ground truth for
    ML training. `features_json` snapshots the feature vector as it was at decision time
    (via the network adapter's build_features()), because issued-item/authorization state
    can drift after the fact and retraining must learn from features-as-observed."""

    __tablename__ = "decision"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), nullable=False, index=True)
    exception_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exception_item.id"), nullable=False, unique=True, index=True
    )

    outcome: Mapped[DecisionOutcome] = mapped_column(
        Enum(DecisionOutcome, name="decision_outcome", native_enum=False, length=10), nullable=False
    )
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    decided_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    features_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
