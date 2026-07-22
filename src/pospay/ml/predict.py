import uuid

from sqlalchemy.orm import Session

from pospay.domain.exception_item import ExceptionItem
from pospay.ml.model import ScoringModel
from pospay.ml.registry import ArtifactStore, get_active_model_row
from pospay.networks.registry import get_adapter

# In-process cache: network_code -> (active_model_id, loaded_model). Invalidated
# automatically whenever the DB's active model id for that network changes (e.g. after a
# retrain promotes a new version) — no explicit cache-bust call needed elsewhere.
_MODEL_CACHE: dict[str, tuple[uuid.UUID, ScoringModel]] = {}


def _load_active_model(session: Session, network_code: str) -> tuple[ScoringModel, str] | None:
    model_row = get_active_model_row(session, network_code)
    if model_row is None:
        return None

    cached = _MODEL_CACHE.get(network_code)
    if cached is not None and cached[0] == model_row.id:
        return cached[1], model_row.version

    model = ArtifactStore().load(model_row.artifact_path)
    _MODEL_CACHE[network_code] = (model_row.id, model)
    return model, model_row.version


def score_exception(session: Session, exception_item: ExceptionItem) -> float | None:
    """Scores an exception with the active model for its network, if one exists yet.
    Returns None (leaving exception_item.ml_score unset) during cold start — matching
    rules/exceptions work fully without ML; a null score means 'not enough data yet to
    score this', never a fabricated 0.5, so the UI can distinguish the two."""
    loaded = _load_active_model(session, exception_item.network_code)
    if loaded is None:
        return None
    model, version = loaded

    adapter = get_adapter(exception_item.network_code)
    features = adapter.build_features(session, exception_item)

    score = float(model.predict_proba([features])[0])
    exception_item.ml_score = score
    exception_item.ml_model_version = version
    return score


def reset_model_cache() -> None:
    """Test-only: force the next score_exception() call to reload from the DB/artifact."""
    _MODEL_CACHE.clear()
