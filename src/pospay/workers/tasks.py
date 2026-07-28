# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pospay.config import get_settings
from pospay.db.session import get_session_factory
from pospay.domain.decision import Decision
from pospay.domain.exception_item import ExceptionItem
from pospay.domain.ml_model import MlModel
from pospay.ml.train import InsufficientTrainingData, train_model
from pospay.networks.registry import registered_codes

logger = logging.getLogger(__name__)


def _count_labeled_decisions(session: Session, network_code: str) -> int:
    stmt = (
        select(Decision.id)
        .join(ExceptionItem, Decision.exception_item_id == ExceptionItem.id)
        .where(ExceptionItem.network_code == network_code, Decision.features_json.is_not(None))
    )
    return len(session.execute(stmt).all())


def _most_recently_trained_count(session: Session, network_code: str, customer_id: uuid.UUID | None = None) -> int:
    stmt = (
        select(MlModel.trained_from_decision_count)
        .where(MlModel.network_code == network_code, MlModel.customer_id == customer_id)
        .order_by(MlModel.created_at.desc())
        .limit(1)
    )
    row = session.execute(stmt).first()
    return row[0] if row else 0


def _customers_with_labeled_decisions(session: Session, network_code: str) -> dict[uuid.UUID, int]:
    """Every customer_id with at least one labeled decision for this network, and how
    many total — the same shape _count_labeled_decisions works with, just grouped by
    customer instead of network-wide. Bank-wide (customer_id is None) exceptions are
    covered by the existing global retrain above, not here."""
    stmt = (
        select(ExceptionItem.customer_id, func.count(Decision.id))
        .select_from(Decision)
        .join(ExceptionItem, Decision.exception_item_id == ExceptionItem.id)
        .where(
            ExceptionItem.network_code == network_code,
            Decision.features_json.is_not(None),
            ExceptionItem.customer_id.is_not(None),
        )
        .group_by(ExceptionItem.customer_id)
    )
    return dict(session.execute(stmt).all())


def retrain_job() -> None:
    """Iterates every registered network and retrains the global model only if enough
    NEW labeled decisions have accumulated since its last training run — avoids
    thrashing on tiny batches. Then does the same per customer: any customer with enough
    new labeled decisions of their own gets their own model trained too, which is what
    actually builds a customer's first model and (via ml/predict.py's AUTO mode) puts it
    into use with no separate action required. Designed to be triggered by an in-process
    APScheduler cron (see workers/scheduler.py, zero-extra-infra for low-barrier
    deployments) or an external cron/Celery-beat/k8s CronJob for enterprise deployments —
    this function is the only thing that needs to be invoked either way."""
    settings = get_settings()
    session = get_session_factory()()
    try:
        for network_code in registered_codes():
            total = _count_labeled_decisions(session, network_code)
            already_trained_on = _most_recently_trained_count(session, network_code)
            new_decisions = total - already_trained_on

            if new_decisions < settings.ml_min_new_decisions_for_retrain:
                logger.info(
                    "Skipping global retrain for %s: %d new decisions, need %d",
                    network_code,
                    new_decisions,
                    settings.ml_min_new_decisions_for_retrain,
                )
            else:
                try:
                    result = train_model(session, network_code)
                    logger.info(
                        "Retrained %s: promoted=%s metrics=%s", network_code, result.promoted, result.metrics
                    )
                except InsufficientTrainingData as exc:
                    logger.info("Skipping global retrain for %s: %s", network_code, exc)

            for customer_id, customer_total in _customers_with_labeled_decisions(session, network_code).items():
                customer_already_trained_on = _most_recently_trained_count(session, network_code, customer_id)
                customer_new_decisions = customer_total - customer_already_trained_on
                if customer_new_decisions < settings.ml_min_new_decisions_for_retrain:
                    continue
                try:
                    result = train_model(session, network_code, customer_id=customer_id)
                    logger.info(
                        "Retrained %s for customer_id=%s: promoted=%s metrics=%s",
                        network_code,
                        customer_id,
                        result.promoted,
                        result.metrics,
                    )
                except InsufficientTrainingData as exc:
                    logger.info("Skipping retrain for %s customer_id=%s: %s", network_code, customer_id, exc)
    finally:
        session.close()
