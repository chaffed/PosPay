# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
from sqlalchemy import select
from sqlalchemy.orm import Session

from pospay.config import get_settings
from pospay.domain.ml_model import MlModel, MlModelStatus
from pospay.ml.model import ScoringModel


class ArtifactStore:
    """Local filesystem by default. Swapping to S3/Blob storage for multi-instance
    enterprise deployments later is a config change here, not a rewrite of train.py/
    predict.py — same pattern as ocr/storage.py."""

    def __init__(self, base_dir: str | None = None) -> None:
        self.base_dir = Path(base_dir or get_settings().ml_artifact_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, model: ScoringModel, key: str) -> str:
        path = self.base_dir / f"{key}.joblib"
        joblib.dump(model, path)
        return str(path)

    def load(self, path: str) -> ScoringModel:
        return joblib.load(path)


def _slot_filter(stmt, *, tenant_id: uuid.UUID | None, customer_id: uuid.UUID | None):
    """A model "slot" — at most one ACTIVE model each (see domain/ml_model.py):
    customer_id given → that customer's model (customer ids are globally unique, so its
    bank doesn't need matching too); otherwise tenant_id given → that bank's bank-only
    model; neither → the shared network model."""
    if customer_id is not None:
        return stmt.where(MlModel.customer_id == customer_id)
    return stmt.where(MlModel.customer_id.is_(None), MlModel.tenant_id == tenant_id)


def get_active_model_row(
    session: Session, network_code: str, customer_id: uuid.UUID | None = None, *, tenant_id: uuid.UUID | None = None
) -> MlModel | None:
    stmt = select(MlModel).where(MlModel.network_code == network_code, MlModel.status == MlModelStatus.ACTIVE)
    return session.execute(_slot_filter(stmt, tenant_id=tenant_id, customer_id=customer_id)).scalars().first()


def list_slot_models(
    session: Session, network_code: str, *, tenant_id: uuid.UUID | None = None, customer_id: uuid.UUID | None = None
) -> list[MlModel]:
    """Every model (any status) in one slot, newest first — the history an admin page shows."""
    stmt = select(MlModel).where(MlModel.network_code == network_code).order_by(MlModel.created_at.desc())
    return list(session.execute(_slot_filter(stmt, tenant_id=tenant_id, customer_id=customer_id)).scalars().all())


def create_model_row(
    session: Session,
    *,
    network_code: str,
    version: str,
    algorithm: str,
    artifact_path: str,
    trained_from_decision_count: int,
    metrics_json: dict[str, Any],
    status: MlModelStatus,
    customer_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
) -> MlModel:
    row = MlModel(
        network_code=network_code,
        customer_id=customer_id,
        tenant_id=tenant_id,
        version=version,
        algorithm=algorithm,
        artifact_path=artifact_path,
        trained_from_decision_count=trained_from_decision_count,
        metrics_json=metrics_json,
        status=status,
        activated_at=datetime.now(timezone.utc) if status == MlModelStatus.ACTIVE else None,
    )
    session.add(row)
    session.flush()
    return row


def activate_model(
    session: Session,
    model_id: uuid.UUID,
    *,
    expected_customer_id: uuid.UUID | None,
    expected_tenant_id: uuid.UUID | None = None,
) -> MlModel:
    """`expected_customer_id` (required) and `expected_tenant_id` name the slot the caller
    means to activate a model in; a model from any other slot is rejected with the same
    "not found" as an unknown id, so this never reveals that it exists. In particular a
    bank can only activate its own bank-only models, and only a caller passing neither
    (the platform operator) can activate a shared-model row."""
    model = session.get(MlModel, model_id)
    if model is None:
        raise ValueError(f"No ml_model with id={model_id}")
    if model.customer_id != expected_customer_id:
        # A stale/unrelated/another-customer's model must never be swappable into a
        # scope it wasn't trained for — keyword-only, no default, so every caller states
        # which scope it expects rather than silently skipping the check.
        raise ValueError(f"No ml_model with id={model_id}")
    if expected_customer_id is None and model.tenant_id != expected_tenant_id:
        raise ValueError(f"No ml_model with id={model_id}")

    # Only retires the previous active row in this SAME slot — shared, bank, and customer
    # models are independent and must never retire each other.
    previous_active = get_active_model_row(session, model.network_code, model.customer_id, tenant_id=model.tenant_id)
    if previous_active is not None and previous_active.id != model.id:
        previous_active.status = MlModelStatus.RETIRED

    model.status = MlModelStatus.ACTIVE
    model.activated_at = datetime.now(timezone.utc)
    session.flush()
    return model
