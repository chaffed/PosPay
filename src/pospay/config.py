# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# The checked-in, publicly-known key pair used for local dev and the test suite (see
# dev_keys/README.md) — every *_private_key_path/*_public_key_path setting below
# defaults to a file under here. assert_production_safe() below refuses to start the
# app with any of these defaults still in place when environment="production".
_DEV_KEYS_DIR = "dev_keys"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="POSPAY_", extra="ignore")

    # Fail-closed on purpose, unlike every other setting here: an operator who sets
    # nothing gets the STRICT behavior (assert_production_safe enforced), not the lax
    # one. Local dev (scripts/launcher.py) and the test suite (tests/conftest.py) both
    # explicitly set POSPAY_ENVIRONMENT=development/test before this is ever read.
    environment: Literal["development", "production"] = "production"

    database_url: str = "sqlite:///./pospay.db"

    # JWT signing (auth/security.py) — ECDSA P-256 key pair, not a shared secret, so it
    # can't be "guessed" the way a hardcoded string could be. Generate your own with
    # scripts/generate_keys.py (see README.md's "Signing keys" section) before deploying;
    # these defaults point at the checked-in dev/test key pair only.
    jwt_private_key_path: str = f"{_DEV_KEYS_DIR}/jwt_private.pem"
    jwt_public_key_path: str = f"{_DEV_KEYS_DIR}/jwt_public.pem"
    jwt_algorithm: str = "ES256"
    # Separate key pair from JWT signing on purpose (bulk_import/signing.py) — a leaked
    # file-signing key shouldn't also let someone forge auth tokens, or vice versa.
    file_signing_private_key_path: str = f"{_DEV_KEYS_DIR}/file_signing_private.pem"
    file_signing_public_key_path: str = f"{_DEV_KEYS_DIR}/file_signing_public.pem"
    # Also a separate key pair from file signing — a distinct key per signed artifact
    # type, same key-separation reasoning (services/audit_log_service.py).
    audit_log_signing_private_key_path: str = f"{_DEV_KEYS_DIR}/audit_log_signing_private.pem"
    audit_log_signing_public_key_path: str = f"{_DEV_KEYS_DIR}/audit_log_signing_public.pem"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_minutes: int = 60 * 24 * 7
    mfa_pending_token_expire_minutes: int = 5  # short-lived: only enough time to complete the WebAuthn ceremony

    # Account lockout (auth/login_service.py::authenticate_password) — global, not
    # per-tenant, same as every other login-security setting here; the two token expiry
    # settings above ARE separately overridable per-tenant (Tenant.access_token_expire_
    # minutes/refresh_token_expire_minutes, see services/tenant_service.py).
    login_max_failed_attempts: int = 5
    login_lockout_minutes: int = 15

    # WebAuthn/FIDO2 — rp_id must be a domain the browser considers the current origin's
    # registrable domain (no scheme/port); origin must be the exact scheme+host(+port).
    # Defaults are dev-only (localhost); set both explicitly for any real deployment.
    webauthn_rp_id: str = "localhost"
    webauthn_rp_name: str = "PosPay"
    webauthn_origin: str = "http://localhost:8000"

    ocr_provider: str = "tesseract"
    # Prevents a pathological/adversarial image from hanging a background-task slot
    # indefinitely — pytesseract raises a plain RuntimeError on timeout, already caught
    # by networks/check/ocr_processing.py's existing broad exception handler.
    ocr_timeout_seconds: int = 30
    check_image_storage_dir: str = "./data/check_images"
    tenant_asset_storage_dir: str = "./data/tenant_assets"
    bulk_upload_storage_dir: str = "./data/bulk_uploads"
    data_export_storage_dir: str = "./data/exports"

    # Resource-exhaustion guards (main.py's request middleware, bulk_import/zip_import.py).
    max_request_body_bytes: int = 50 * 1024 * 1024
    # Decompressed zip content can reasonably exceed the wire size of the compressed
    # upload itself, hence a separate, larger cap than max_request_body_bytes.
    max_zip_uncompressed_bytes: int = 200 * 1024 * 1024

    check_stale_date_default_days: int = 180
    payee_match_fuzzy_threshold: float = 85.0

    ml_min_new_decisions_for_retrain: int = 20
    # Minimum time between two retrains of the same (network_code, customer_id) pair —
    # closes off repeatedly hammering the on-demand retrain endpoint into a self-service
    # compute DoS (ml/train.py::train_model). The nightly scheduled job is already gated
    # by ml_min_new_decisions_for_retrain and won't normally trip this too.
    ml_retrain_cooldown_seconds: int = 60
    ml_artifact_dir: str = "./ml_artifacts"  # NOT inside src/pospay/ — that's installed package code, not a place for runtime output
    enable_ml_scheduler: bool = False  # opt-in: off by default so tests/local dev don't spawn a background thread
    ml_retrain_cron_hour: int = 2  # nightly at 2am when enabled

    # Federated login (auth/oidc_service.py, services/sso_service.py) — fed through a KDF
    # into a valid Fernet key (auth/crypto.py), so this stays a plain string like every
    # other *_secret_key setting rather than a hand-generated base64 Fernet key. This is
    # ENCRYPTION (of stored SSO client secrets), not signing, so it deliberately doesn't
    # move to a key pair like jwt/file_signing/audit_log_signing above — but it still
    # needs a real random value in production, enforced below.
    sso_encryption_key: str = "dev-secret-change-me-32-bytes-minimum-for-sso"
    oidc_http_timeout_seconds: float = 10.0
    # Override for the redirect_uri host when a deployment sits behind a proxy that
    # doesn't forward the original scheme/host correctly — same class of caveat as
    # webauthn_origin. None (default) derives it from the live request instead.
    public_base_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Every setting here that still equals its checked-in dev/test default is a genuine
# security hole if it ever reaches a real deployment (see SECURITY_REVIEW.md) — a
# hardcoded default field() a caller might just never override. Checked once at app
# startup (main.py::create_app), not lazily, so a misconfigured production deployment
# fails immediately and loudly rather than serving requests insecurely.
_DEFAULT_FIELDS: tuple[str, ...] = (
    "jwt_private_key_path",
    "jwt_public_key_path",
    "file_signing_private_key_path",
    "file_signing_public_key_path",
    "audit_log_signing_private_key_path",
    "audit_log_signing_public_key_path",
    "sso_encryption_key",
)


def assert_production_safe(settings: Settings) -> None:
    if settings.environment != "production":
        return
    defaults = Settings.model_fields
    still_default = [name for name in _DEFAULT_FIELDS if getattr(settings, name) == defaults[name].default]
    if still_default:
        raise RuntimeError(
            "Refusing to start with POSPAY_ENVIRONMENT=production while these settings "
            f"are still at their insecure checked-in dev/test defaults: {', '.join(still_default)}. "
            "Generate real ones with `python scripts/generate_keys.py` and a random "
            "POSPAY_SSO_ENCRYPTION_KEY — see README.md's 'Signing keys' section."
        )
