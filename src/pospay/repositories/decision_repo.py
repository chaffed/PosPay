from pospay.domain.decision import Decision
from pospay.repositories.base import TenantScopedRepository


class DecisionRepository(TenantScopedRepository[Decision]):
    model = Decision
