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
    # Also its own separate key pair — signed Written Statement of Unauthorized Debit
    # attestations (services/wsud_service.py) are a distinct signed-artifact type from
    # the three above, same key-separation reasoning.
    wsud_signing_private_key_path: str = f"{_DEV_KEYS_DIR}/wsud_signing_private.pem"
    wsud_signing_public_key_path: str = f"{_DEV_KEYS_DIR}/wsud_signing_public.pem"
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

    # Bounds a single data-export archive (services/data_export_service.py) — a technical
    # ceiling on how much any one entity can dump into an archive, not a per-tenant
    # policy value like the timeout below, so it's global-only (no Tenant override).
    data_export_max_rows_per_entity: int = 50_000
    # Per-tenant override on Tenant.data_export_timeout_seconds (None there means "use
    # this"), same nullable-override shape as jwt_access/refresh_token_expire_minutes.
    data_export_timeout_seconds: int = 300

    ml_min_new_decisions_for_retrain: int = 20
    # Minimum time between two retrains of the same (network_code, customer_id) pair —
    # closes off repeatedly hammering the on-demand retrain endpoint into a self-service
    # compute DoS (ml/train.py::train_model). The nightly scheduled job is already gated
    # by ml_min_new_decisions_for_retrain and won't normally trip this too.
    ml_retrain_cooldown_seconds: int = 60
    ml_artifact_dir: str = "./ml_artifacts"  # NOT inside src/pospay/ — that's installed package code, not a place for runtime output
    enable_ml_scheduler: bool = False  # opt-in: off by default so tests/local dev don't spawn a background thread
    ml_retrain_cron_hour: int = 2  # nightly at 2am when enabled

    # Auto-import dropbox (services/dropbox_import_service.py) — a directory tree an
    # external system (a core-banking export, an SFTP drop) can land files into for
    # unattended import, isolated by tenant slug (and optionally customer number)
    # subdirectory — see that module for the exact layout.
    auto_import_dropbox_dir: str = "./data/auto_import_dropbox"
    auto_import_enabled: bool = False  # opt-in: off by default, same reasoning as enable_ml_scheduler
    auto_import_interval_seconds: int = 300  # how often the in-app scheduler polls, when enabled
    # A dropped file is only processed once its mtime is at least this old — a simple,
    # sender-agnostic guard against reading a file an external system is still mid-write
    # on, without requiring that system to adopt a write-then-atomic-rename convention.
    auto_import_min_file_age_seconds: int = 30
    # Same resource-exhaustion-guard reasoning as max_request_body_bytes, applied to a
    # dropped file read directly off disk rather than an HTTP upload.
    auto_import_max_file_bytes: int = 50 * 1024 * 1024

    # Notifications (services/notification_service.py queues, workers/tasks.py::
    # notification_dispatch_job drains) — email/SMS are never sent inline in a request,
    # so a slow/unreachable provider never blocks the action that triggered it.
    notifications_enabled: bool = False  # opt-in: off by default, same reasoning as enable_ml_scheduler
    notification_dispatch_interval_seconds: int = 30
    notification_dispatch_batch_size: int = 200
    email_provider: str = "smtp"  # see notifications/email/factory.py

    # Default disposition (services/auto_disposition_service.py, workers/tasks.py::
    # sweep_expired_dispositions_job) — auto-decides an exception whose decision_deadline
    # has passed with no human decision, per a per-customer CustomerDispositionSetting.
    enable_disposition_scheduler: bool = False  # opt-in: off by default, same reasoning as enable_ml_scheduler
    disposition_sweep_interval_seconds: int = 300
    # Fallback for CustomerDispositionSetting.response_window_hours when a customer's own
    # setting leaves it unset — same nullable-override-falls-back-to-global-default shape
    # as data_export_timeout_seconds above.
    default_disposition_response_window_hours: int = 24

    # Persistent sales-demo tenant (services/demo_tenant_service.py) — a fully-seeded,
    # real tenant that resets to its pristine state the next time anyone logs into it
    # after its own (short) session window has elapsed. Off by default; a password must
    # also be set, since there's no safe hardcoded default for a real credential.
    demo_tenant_enabled: bool = False
    demo_tenant_password: str | None = None
    demo_tenant_session_minutes: int = 60

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    smtp_from_address: str = "notifications@pospay.local"
    smtp_timeout_seconds: float = 10.0
    sms_provider: str = "twilio"  # see notifications/sms/factory.py; requires pip install pospay[sms]
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_number: str | None = None

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
    "wsud_signing_private_key_path",
    "wsud_signing_public_key_path",
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
