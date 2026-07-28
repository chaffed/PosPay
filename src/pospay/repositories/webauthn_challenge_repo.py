# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from pospay.domain.webauthn_challenge import WebauthnChallenge
from pospay.repositories.base import TenantScopedRepository


class WebauthnChallengeRepository(TenantScopedRepository[WebauthnChallenge]):
    model = WebauthnChallenge
