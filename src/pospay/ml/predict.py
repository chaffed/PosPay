# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import uuid

from sqlalchemy.orm import Session

from pospay.domain.customer_ml_setting import MlScoringMode
from pospay.domain.exception_item import ExceptionItem
from pospay.domain.ml_model import MlModel
from pospay.ml.model import ScoringModel
from pospay.ml.registry import ArtifactStore, get_active_model_row
from pospay.networks.registry import get_adapter
from pospay.repositories.customer_ml_setting_repo import CustomerMlSettingRepository

# In-process cache: (network_code, customer_id) -> (active_model_id, loaded_model).
# customer_id is None for the global model's own cache slot, so it never collides with
# any customer's. Invalidated automatically whenever the DB's active model id for that
# slot changes (e.g. after a retrain promotes a new version) — no explicit cache-bust
# call needed elsewhere.
_MODEL_CACHE: dict[tuple[str, uuid.UUID | None], tuple[uuid.UUID, ScoringModel]] = {}


def _resolve_scoring_source(
    session: Session, tenant_id: uuid.UUID, network_code: str, customer_id: uuid.UUID | None
) -> MlModel | None:
    """Picks which MlModel row (global vs this customer's own) an exception should be
    scored with. A bank-wide exception (customer_id is None) always uses the global
    model — customer-specific models only ever apply to a customer-scoped exception.

    Absence of a CustomerMlSetting row means AUTO (see that model's docstring): use the
    customer's own active model once one exists, otherwise fall back to global. This is
    the actual auto-switch — the moment a retrain promotes a customer's first model to
    ACTIVE, the very next exception scored for them picks it up with no separate
    "switch" action needed. GLOBAL pins to the global model regardless; CUSTOMER pins to
    the customer model but still falls back to global if none is active yet (same
    graceful cold-start degradation as everywhere else in this module — never an error)."""
    global_model = get_active_model_row(session, network_code)
    if customer_id is None:
        return global_model

    settings = CustomerMlSettingRepository(session, tenant_id).list(customer_id=customer_id, network_code=network_code)
    mode = settings[0].mode if settings else MlScoringMode.AUTO

    if mode == MlScoringMode.GLOBAL:
        return global_model

    customer_model = get_active_model_row(session, network_code, customer_id)
    if mode == MlScoringMode.CUSTOMER:
        return customer_model or global_model

    # AUTO
    return customer_model or global_model


def _load_model(session: Session, tenant_id: uuid.UUID, network_code: str, customer_id: uuid.UUID | None) -> tuple[ScoringModel, str] | None:
    model_row = _resolve_scoring_source(session, tenant_id, network_code, customer_id)
    if model_row is None:
        return None

    cache_key = (network_code, model_row.customer_id)
    cached = _MODEL_CACHE.get(cache_key)
    if cached is not None and cached[0] == model_row.id:
        return cached[1], model_row.version

    model = ArtifactStore().load(model_row.artifact_path)
    _MODEL_CACHE[cache_key] = (model_row.id, model)
    return model, model_row.version


def score_exception(session: Session, exception_item: ExceptionItem) -> float | None:
    """Scores an exception with whichever model (global or its customer's own — see
    _resolve_scoring_source) currently applies, if one exists yet. Returns None (leaving
    exception_item.ml_score unset) during cold start — matching rules/exceptions work
    fully without ML; a null score means 'not enough data yet to score this', never a
    fabricated 0.5, so the UI can distinguish the two."""
    loaded = _load_model(session, exception_item.tenant_id, exception_item.network_code, exception_item.customer_id)
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
