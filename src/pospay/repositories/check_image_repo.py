# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from pospay.domain.check_image import CheckImage
from pospay.repositories.base import TenantScopedRepository


class CheckImageRepository(TenantScopedRepository[CheckImage]):
    model = CheckImage
