from pospay.domain.bulk_upload_file import BulkUploadFile
from pospay.repositories.base import TenantScopedRepository


class BulkUploadFileRepository(TenantScopedRepository[BulkUploadFile]):
    model = BulkUploadFile
