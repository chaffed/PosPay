# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import pytest

from pospay.config import Settings, assert_production_safe

_OVERRIDDEN = {
    "jwt_private_key_path": "keys/jwt_private.pem",
    "jwt_public_key_path": "keys/jwt_public.pem",
    "file_signing_private_key_path": "keys/file_signing_private.pem",
    "file_signing_public_key_path": "keys/file_signing_public.pem",
    "audit_log_signing_private_key_path": "keys/audit_log_signing_private.pem",
    "audit_log_signing_public_key_path": "keys/audit_log_signing_public.pem",
    "sso_encryption_key": "a-real-random-secret-not-the-checked-in-default",
}


def test_development_environment_never_raises_even_with_all_defaults():
    settings = Settings(environment="development")
    assert_production_safe(settings)  # must not raise


def test_production_environment_raises_with_all_defaults():
    settings = Settings(environment="production")
    with pytest.raises(RuntimeError, match="insecure checked-in dev/test defaults"):
        assert_production_safe(settings)


def test_production_environment_passes_once_every_default_is_overridden():
    settings = Settings(environment="production", **_OVERRIDDEN)
    assert_production_safe(settings)  # must not raise


@pytest.mark.parametrize("field_left_default", list(_OVERRIDDEN))
def test_production_environment_raises_if_any_single_field_still_default(field_left_default):
    overrides = {k: v for k, v in _OVERRIDDEN.items() if k != field_left_default}
    settings = Settings(environment="production", **overrides)
    with pytest.raises(RuntimeError, match=field_left_default):
        assert_production_safe(settings)
