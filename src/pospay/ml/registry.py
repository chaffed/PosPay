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


def get_active_model_row(session: Session, network_code: str) -> MlModel | None:
    stmt = select(MlModel).where(MlModel.network_code == network_code, MlModel.status == MlModelStatus.ACTIVE)
    return session.execute(stmt).scalars().first()


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
) -> MlModel:
    row = MlModel(
        network_code=network_code,
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


def activate_model(session: Session, model_id: uuid.UUID) -> MlModel:
    model = session.get(MlModel, model_id)
    if model is None:
        raise ValueError(f"No ml_model with id={model_id}")

    previous_active = get_active_model_row(session, model.network_code)
    if previous_active is not None and previous_active.id != model.id:
        previous_active.status = MlModelStatus.RETIRED

    model.status = MlModelStatus.ACTIVE
    model.activated_at = datetime.now(timezone.utc)
    session.flush()
    return model
