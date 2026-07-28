# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from pospay.domain.customer_ml_setting import CustomerMlSetting
from pospay.repositories.base import TenantScopedRepository


class CustomerMlSettingRepository(TenantScopedRepository[CustomerMlSetting]):
    model = CustomerMlSetting
