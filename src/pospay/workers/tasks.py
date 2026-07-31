# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pospay.config import get_settings
from pospay.db.session import get_session_factory
from pospay.domain.decision import Decision
from pospay.domain.exception_item import ExceptionItem
from pospay.domain.ml_model import MlModel, MlModelStatus
from pospay.domain.notification import Notification, NotificationChannel, NotificationStatus
from pospay.ml.registry import create_model_row
from pospay.ml.train import InsufficientTrainingData, RetrainCooldownActive, train_model
from pospay.networks.registry import registered_codes
from pospay.notifications.email.factory import get_email_provider
from pospay.notifications.sms.factory import get_sms_provider
from pospay.services.dropbox_import_service import scan_and_import_all_tenants

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


def _train_and_log(session: Session, network_code: str, *, customer_id: uuid.UUID | None = None, label: str = "global") -> None:
    """Runs train_model for one (network_code, customer_id) pair as part of the
    unattended scheduled job, and never lets a single network/customer's failure abort
    the rest of the run — unlike the on-demand web/API routes (where a human is watching
    the request and an HTTP error is enough), an uncaught exception here would otherwise
    silently skip every network/customer still left in retrain_job()'s loops. An
    unexpected failure (not just the two already-expected "nothing to do yet" outcomes)
    is recorded as a FAILED MlModel row so it's visible on the admin models page, not
    just a server log line nobody looks at."""
    try:
        result = train_model(session, network_code, customer_id=customer_id)
        logger.info("Retrained %s (%s): promoted=%s metrics=%s", network_code, label, result.promoted, result.metrics)
    except InsufficientTrainingData as exc:
        logger.info("Skipping retrain for %s (%s): %s", network_code, label, exc)
    except RetrainCooldownActive as exc:
        logger.info("Retrain for %s (%s) still in cooldown: %s", network_code, label, exc)
    except Exception as exc:  # noqa: BLE001 — isolate one network/customer's failure from the rest of the run
        logger.exception("Retrain failed for %s (%s)", network_code, label)
        session.rollback()
        create_model_row(
            session,
            network_code=network_code,
            customer_id=customer_id,
            version=f"failed_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}",
            algorithm="logistic_regression",
            artifact_path="",
            trained_from_decision_count=0,
            metrics_json={"error": str(exc)},
            status=MlModelStatus.FAILED,
        )
        session.commit()


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
                _train_and_log(session, network_code)

            for customer_id, customer_total in _customers_with_labeled_decisions(session, network_code).items():
                customer_already_trained_on = _most_recently_trained_count(session, network_code, customer_id)
                customer_new_decisions = customer_total - customer_already_trained_on
                if customer_new_decisions < settings.ml_min_new_decisions_for_retrain:
                    continue
                _train_and_log(session, network_code, customer_id=customer_id, label=f"customer_id={customer_id}")
    finally:
        session.close()


def dropbox_import_job() -> None:
    """The in-app scheduler's entry point for the auto-import dropbox (see
    services/dropbox_import_service.py) -- one session, one full scan of every tenant's
    own subtree, same call scripts/import_dropbox.py and the scheduler itself both make."""
    session = get_session_factory()()
    try:
        results = scan_and_import_all_tenants(session)
        imported = sum(r.outcome == "imported" for r in results)
        failed = sum(r.outcome == "failed" for r in results)
        duplicates = sum(r.outcome == "duplicate" for r in results)
        logger.info("Dropbox import scan: %d imported, %d failed, %d duplicates skipped", imported, failed, duplicates)
    finally:
        session.close()


def _send_one_notification(notification: Notification) -> None:
    if notification.channel == NotificationChannel.EMAIL:
        get_email_provider().send(to=notification.destination, subject=notification.subject or "", body=notification.body)
    else:
        get_sms_provider().send(to=notification.destination, body=notification.body)


def notification_dispatch_job() -> None:
    """Drains PENDING Notification rows (services/notification_service.py queues them,
    never sends) -- one row's failure never blocks the rest of the batch, same isolation
    principle as _train_and_log/dropbox_import_job's own per-item try/except. Committed
    per-row so partial progress survives a crash mid-run rather than re-sending
    everything already-successful on the next poll."""
    settings = get_settings()
    session = get_session_factory()()
    try:
        rows = (
            session.execute(
                select(Notification)
                .where(Notification.status == NotificationStatus.PENDING)
                .order_by(Notification.created_at)
                .limit(settings.notification_dispatch_batch_size)
            )
            .scalars()
            .all()
        )

        sent = 0
        retrying = 0
        failed = 0
        for notification in rows:
            try:
                _send_one_notification(notification)
            except Exception as exc:  # noqa: BLE001 -- one bad destination/provider hiccup must never abort the batch
                notification.attempt_count += 1
                notification.error = str(exc)[:1000]
                if notification.exhausted_retries:
                    notification.status = NotificationStatus.FAILED
                    failed += 1
                else:
                    retrying += 1  # stays PENDING -- picked up again next poll
                logger.warning(
                    "Failed to send notification %s (%s, attempt %d, %s): %s",
                    notification.id, notification.channel.value, notification.attempt_count,
                    "giving up" if notification.exhausted_retries else "will retry", exc,
                )
            else:
                notification.status = NotificationStatus.SENT
                notification.sent_at = datetime.now(timezone.utc)
                sent += 1
            session.commit()

        if rows:
            logger.info("Notification dispatch: %d sent, %d retrying, %d permanently failed", sent, retrying, failed)
    finally:
        session.close()
