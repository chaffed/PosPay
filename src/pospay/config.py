from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="POSPAY_", extra="ignore")

    database_url: str = "sqlite:///./pospay.db"

    jwt_secret_key: str = "dev-secret-change-me-32-bytes-minimum-for-hs256"
    jwt_algorithm: str = "HS256"
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

    check_stale_date_default_days: int = 180
    payee_match_fuzzy_threshold: float = 85.0

    ml_min_new_decisions_for_retrain: int = 20
    ml_artifact_dir: str = "./ml_artifacts"  # NOT inside src/pospay/ — that's installed package code, not a place for runtime output
    enable_ml_scheduler: bool = False  # opt-in: off by default so tests/local dev don't spawn a background thread
    ml_retrain_cron_hour: int = 2  # nightly at 2am when enabled


@lru_cache
def get_settings() -> Settings:
    return Settings()
