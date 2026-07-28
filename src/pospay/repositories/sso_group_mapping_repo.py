# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from pospay.domain.sso_connection import SsoGroupMapping
from pospay.repositories.base import TenantScopedRepository


class SsoGroupMappingRepository(TenantScopedRepository[SsoGroupMapping]):
    model = SsoGroupMapping
