# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from pospay.domain.ach_authorization_rule import AchAuthorizationRule
from pospay.repositories.base import CustomerScopedRepository


class AchAuthorizationRepository(CustomerScopedRepository[AchAuthorizationRule]):
    model = AchAuthorizationRule
