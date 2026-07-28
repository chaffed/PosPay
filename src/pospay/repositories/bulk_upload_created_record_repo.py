from pospay.domain.bulk_upload_created_record import BulkUploadCreatedRecord
from pospay.repositories.base import TenantScopedRepository


class BulkUploadCreatedRecordRepository(TenantScopedRepository[BulkUploadCreatedRecord]):
    model = BulkUploadCreatedRecord
