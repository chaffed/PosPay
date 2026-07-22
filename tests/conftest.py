import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pospay.auth.security import hash_password
from pospay.db.base import Base
from pospay.db.session import get_db
from pospay.domain.account import Account
from pospay.domain.payment_network import PaymentNetwork, SettlementTiming
from pospay.domain.tenant import Tenant
from pospay.domain.user import User, UserRole

# pospay.domain's __init__ imports every model module, fully populating Base.metadata
# before create_all — see its docstring for why this must be centralized in one place.
import pospay.domain  # noqa: F401


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_pragma(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                PaymentNetwork(code="check", name="Check", settlement_timing=SettlementTiming.ASYNC_REVIEWABLE),
                PaymentNetwork(code="ach", name="ACH", settlement_timing=SettlementTiming.ASYNC_REVIEWABLE),
            ]
        )
        session.commit()
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db_session(session_factory) -> Generator[Session, None, None]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


class TenantFactory:
    """Creates a tenant plus one user of each role, all with a known plaintext password,
    for tests that need a fully-authenticated multi-role scenario without repeating
    boilerplate. `make()` returns a dict of {role_name: (User, plain_password)}."""

    PASSWORD = "test-password-123"

    def __init__(self, session: Session):
        self.session = session

    def make(self, *, name: str = "Acme Corp", slug: str | None = None, require_dual_control: bool = False):
        slug = slug or f"acme-{uuid.uuid4().hex[:8]}"
        tenant = Tenant(name=name, slug=slug, require_dual_control=require_dual_control)
        self.session.add(tenant)
        self.session.flush()

        account = Account(tenant_id=tenant.id, account_number="0001", name="Operating")
        self.session.add(account)

        users = {}
        for role in UserRole:
            user = User(
                tenant_id=tenant.id,
                email=f"{role.value}@{slug}.example.com",
                hashed_password=hash_password(self.PASSWORD),
                role=role,
            )
            self.session.add(user)
            users[role.value] = user

        self.session.commit()
        return tenant, account, users


@pytest.fixture
def tenant_factory(db_session) -> TenantFactory:
    return TenantFactory(db_session)


@pytest.fixture
def app(session_factory):
    from pospay.main import create_app

    app = create_app()

    def _override_get_db() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    return app


@pytest.fixture
def client(app) -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


def login_headers(client: TestClient, tenant_slug: str, email: str, password: str = TenantFactory.PASSWORD) -> dict:
    resp = client.post(
        "/api/v1/auth/login", json={"tenant_slug": tenant_slug, "email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}
