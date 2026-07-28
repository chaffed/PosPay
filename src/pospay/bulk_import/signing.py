# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

import hashlib
import hmac

from pospay.config import get_settings


def content_hash(data: bytes) -> str:
    """A plain content fingerprint — informational, quotable in an audit report
    independent of the server's signing secret. NOT the tamper-evidence mechanism itself
    (see sign_file/verify_signature for that); anyone who can edit the DB row could
    recompute and replace this alongside a tampered file."""
    return hashlib.sha256(data).hexdigest()


def sign_file(data: bytes) -> str:
    """HMAC-SHA256 over the raw file bytes using a server-held secret
    (config.Settings.file_signing_secret) — same pattern already used for JWTs
    (auth/security.py's HS256 signing). Only someone with the secret can produce a
    signature that verify_signature will accept, which is what makes this actual
    tamper-evidence rather than just a checksum."""
    secret = get_settings().file_signing_secret.encode("utf-8")
    return hmac.new(secret, data, hashlib.sha256).hexdigest()


def verify_signature(data: bytes, signature: str) -> bool:
    """Constant-time comparison (hmac.compare_digest) — same care already taken for CSRF
    token comparison in web/security.py, to avoid a timing side-channel on the check
    itself."""
    return hmac.compare_digest(sign_file(data), signature)
