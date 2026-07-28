from pospay.domain.ach_authorization_rule import AchAuthorizationRule
from pospay.repositories.base import CustomerScopedRepository


class AchAuthorizationRepository(CustomerScopedRepository[AchAuthorizationRule]):
    model = AchAuthorizationRule
