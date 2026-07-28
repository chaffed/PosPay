# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="POSPAY_", extra="ignore")

    database_url: str = "sqlite:///./pospay.db"

    jwt_secret_key: str = "dev-secret-change-me-32-bytes-minimum-for-hs256"
    jwt_algorithm: str = "HS256"
    # Separate from jwt_secret_key on purpose (bulk_import/signing.py) — a leaked
    # file-signing secret shouldn't also let someone forge auth tokens, or vice versa.
    file_signing_secret: str = "dev-secret-change-me-32-bytes-minimum-for-hmac"
    # Also separate from file_signing_secret — a distinct secret per signed artifact type,
    # same key-separation reasoning (services/audit_log_service.py).
    audit_log_signing_secret: str = "dev-secret-change-me-32-bytes-minimum-for-audit-hmac"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_minutes: int = 60 * 24 * 7
    mfa_pending_token_expire_minutes: int = 5  # short-lived: only enough time to complete the WebAuthn ceremony

    # WebAuthn/FIDO2 — rp_id must be a domain the browser considers the current origin's
    # registrable domain (no scheme/port); origin must be the exact scheme+host(+port).
    # Defaults are dev-only (localhost); set both explicitly for any real deployment.
    webauthn_rp_id: str = "localhost"
    webauthn_rp_name: str = "PosPay"
    webauthn_origin: str = "http://localhost:8000"

    ocr_provider: str = "tesseract"
    check_image_storage_dir: str = "./data/check_images"
    tenant_asset_storage_dir: str = "./data/tenant_assets"
    bulk_upload_storage_dir: str = "./data/bulk_uploads"
    data_export_storage_dir: str = "./data/exports"

    check_stale_date_default_days: int = 180
    payee_match_fuzzy_threshold: float = 85.0

    ml_min_new_decisions_for_retrain: int = 20
    ml_artifact_dir: str = "./ml_artifacts"  # NOT inside src/pospay/ — that's installed package code, not a place for runtime output
    enable_ml_scheduler: bool = False  # opt-in: off by default so tests/local dev don't spawn a background thread
    ml_retrain_cron_hour: int = 2  # nightly at 2am when enabled

    # Federated login (auth/oidc_service.py, services/sso_service.py) — fed through a KDF
    # into a valid Fernet key (auth/crypto.py), so this stays a plain string like every
    # other *_secret_key setting rather than a hand-generated base64 Fernet key.
    sso_encryption_key: str = "dev-secret-change-me-32-bytes-minimum-for-sso"
    oidc_http_timeout_seconds: float = 10.0
    # Override for the redirect_uri host when a deployment sits behind a proxy that
    # doesn't forward the original scheme/host correctly — same class of caveat as
    # webauthn_origin. None (default) derives it from the live request instead.
    public_base_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
