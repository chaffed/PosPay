from pospay.domain.webauthn_challenge import WebauthnChallenge
from pospay.repositories.base import TenantScopedRepository


class WebauthnChallengeRepository(TenantScopedRepository[WebauthnChallenge]):
    model = WebauthnChallenge
