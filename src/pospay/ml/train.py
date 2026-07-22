from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from pospay.domain.decision import Decision, DecisionOutcome
from pospay.domain.exception_item import ExceptionItem
from pospay.domain.ml_model import MlModel, MlModelStatus
from pospay.ml.model import LogisticRegressionScoringModel
from pospay.ml.registry import ArtifactStore, activate_model, create_model_row, get_active_model_row

MIN_DECISIONS_TO_TRAIN = 10
_HOLDOUT_FRACTION = 0.2


class InsufficientTrainingData(Exception):
    pass


@dataclass(frozen=True, slots=True)
class TrainResult:
    model_row: MlModel
    promoted: bool
    metrics: dict[str, float]


def _load_labeled_decisions(session: Session, network_code: str) -> list[Decision]:
    stmt = (
        select(Decision)
        .join(ExceptionItem, Decision.exception_item_id == ExceptionItem.id)
        .where(ExceptionItem.network_code == network_code, Decision.features_json.is_not(None))
        .order_by(Decision.decided_at)
    )
    return list(session.execute(stmt).scalars().all())


def _safe_metrics(y_true: list[int], y_pred_proba, y_pred: list[int]) -> dict[str, float]:
    from sklearn.metrics import precision_score, recall_score, roc_auc_score

    metrics = {
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
    }
    # AUC is undefined with only one class present in the holdout — common with small/
    # early datasets; skip rather than crash the whole training run over it.
    if len(set(y_true)) > 1:
        metrics["auc"] = float(roc_auc_score(y_true, y_pred_proba))
    return metrics


def train_model(session: Session, network_code: str) -> TrainResult:
    decisions = _load_labeled_decisions(session, network_code)
    if len(decisions) < MIN_DECISIONS_TO_TRAIN:
        raise InsufficientTrainingData(
            f"Only {len(decisions)} labeled decisions for network_code={network_code!r}, "
            f"need at least {MIN_DECISIONS_TO_TRAIN}."
        )

    X = [d.features_json for d in decisions]
    y = [1 if d.outcome == DecisionOutcome.PAY else 0 for d in decisions]

    split_index = max(1, int(len(decisions) * (1 - _HOLDOUT_FRACTION)))
    split_index = min(split_index, len(decisions) - 1)  # always leave >=1 holdout row
    X_train, X_holdout = X[:split_index], X[split_index:]
    y_train, y_holdout = y[:split_index], y[split_index:]

    model = LogisticRegressionScoringModel()
    model.fit(X_train, y_train)

    holdout_proba = model.predict_proba(X_holdout)
    holdout_pred = [1 if p >= 0.5 else 0 for p in holdout_proba]
    metrics = _safe_metrics(y_holdout, holdout_proba, holdout_pred)

    existing_model_count = session.execute(
        select(MlModel).where(MlModel.network_code == network_code)
    ).scalars().all()
    version = f"v{len(existing_model_count) + 1}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"

    artifact_path = ArtifactStore().save(model, key=f"{network_code}_{version}")

    current_active = get_active_model_row(session, network_code)
    promote = current_active is None or metrics.get("auc", 0.0) >= (current_active.metrics_json or {}).get("auc", 0.0)

    model_row = create_model_row(
        session,
        network_code=network_code,
        version=version,
        algorithm="logistic_regression",
        artifact_path=artifact_path,
        trained_from_decision_count=len(decisions),
        metrics_json=metrics,
        status=MlModelStatus.TRAINING,
    )

    if promote:
        activate_model(session, model_row.id)
    else:
        model_row.status = MlModelStatus.RETIRED

    session.commit()
    return TrainResult(model_row=model_row, promoted=promote, metrics=metrics)
