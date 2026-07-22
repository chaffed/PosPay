from pospay.domain.check_image import CheckImage
from pospay.repositories.base import TenantScopedRepository


class CheckImageRepository(TenantScopedRepository[CheckImage]):
    model = CheckImage
