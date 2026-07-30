# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from pospay.domain.ach_return_reason import AchReturnReason
from pospay.repositories.base import TenantScopedRepository


class AchReturnReasonRepository(TenantScopedRepository[AchReturnReason]):
    model = AchReturnReason
