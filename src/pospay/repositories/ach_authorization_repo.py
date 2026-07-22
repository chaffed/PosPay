from pospay.domain.ach_authorization_rule import AchAuthorizationRule
from pospay.repositories.base import TenantScopedRepository


class AchAuthorizationRepository(TenantScopedRepository[AchAuthorizationRule]):
    model = AchAuthorizationRule
