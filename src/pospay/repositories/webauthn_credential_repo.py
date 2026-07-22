from pospay.domain.webauthn_credential import WebauthnCredential
from pospay.repositories.base import TenantScopedRepository


class WebauthnCredentialRepository(TenantScopedRepository[WebauthnCredential]):
    model = WebauthnCredential
