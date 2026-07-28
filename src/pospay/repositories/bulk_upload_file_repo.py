# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from pospay.domain.bulk_upload_file import BulkUploadFile
from pospay.repositories.base import TenantScopedRepository


class BulkUploadFileRepository(TenantScopedRepository[BulkUploadFile]):
    model = BulkUploadFile
