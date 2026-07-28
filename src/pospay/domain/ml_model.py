# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from pospay.db.base import Base, new_uuid


class MlModelStatus(str, enum.Enum):
    TRAINING = "training"
    ACTIVE = "active"
    RETIRED = "retired"
    FAILED = "failed"


class MlModel(Base):
    """Model registry, one row per trained artifact. Separate models per network_code
    (check vs ach feature spaces barely overlap) — never assume a single global model.

    customer_id is None for the global, network-wide model (the original and still
    default meaning of this table) or set to scope a row to one customer's own model for
    that network (see ml/train.py, ml/predict.py). A given (network_code, customer_id)
    pair can have at most one ACTIVE row at a time — enforced in ml/registry.py, not a DB
    constraint, since TRAINING/RETIRED/FAILED rows for the same pair are expected to
    coexist as history."""

    __tablename__ = "ml_model"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    network_code: Mapped[str] = mapped_column(ForeignKey("payment_network.code"), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customer.id"), nullable=True, index=True)

    version: Mapped[str] = mapped_column(String(64), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_path: Mapped[str] = mapped_column(String(500), nullable=False)

    trained_from_decision_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    status: Mapped[MlModelStatus] = mapped_column(
        Enum(MlModelStatus, name="ml_model_status", native_enum=False, length=20),
        nullable=False,
        default=MlModelStatus.TRAINING,
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
