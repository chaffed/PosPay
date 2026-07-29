# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from pospay.domain.check_image import CheckImage
from pospay.repositories.base import CustomerScopedRepository


class CheckImageRepository(CustomerScopedRepository[CheckImage]):
    model = CheckImage
