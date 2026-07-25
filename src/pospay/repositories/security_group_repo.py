from pospay.domain.security_group import SecurityGroup
from pospay.repositories.base import TenantScopedRepository


class SecurityGroupRepository(TenantScopedRepository[SecurityGroup]):
    model = SecurityGroup
