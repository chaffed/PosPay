import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


class TenantScopedRepository(Generic[ModelT]):
    """Base for all data access on tenant-owned tables. This is THE enforcement point for
    multi-tenant isolation: every read filters on tenant_id, and add() stamps tenant_id
    from the authenticated context rather than trusting a caller-supplied value. tenant_id
    must always originate from the JWT (see db/tenancy.TenantContext / auth/deps.py),
    never from a request body or path parameter — that's what would let one tenant read or
    write another tenant's rows."""

    model: type[ModelT]

    def __init__(self, session: Session, tenant_id: uuid.UUID):
        self.session = session
        self.tenant_id = tenant_id

    def query(self) -> Select:
        return select(self.model).where(self.model.tenant_id == self.tenant_id)

    def get(self, id_: uuid.UUID) -> ModelT | None:
        stmt = self.query().where(self.model.id == id_)
        return self.session.execute(stmt).scalar_one_or_none()

    def list(self, **equality_filters: Any) -> list[ModelT]:
        stmt = self.query()
        for column_name, value in equality_filters.items():
            if value is not None:
                stmt = stmt.where(getattr(self.model, column_name) == value)
        return list(self.session.execute(stmt).scalars().all())

    def add(self, obj: ModelT) -> ModelT:
        obj.tenant_id = self.tenant_id
        self.session.add(obj)
        return obj


class CustomerScopedRepository(TenantScopedRepository[ModelT]):
    """For the six tables that can additionally be scoped to one Customer within a
    tenant (domain/customer.py, TenantMembership.customer_id): Account, IssuedItem,
    StopPayment, PaidItem, AchAuthorizationRule, AchTransaction. When customer_id is None
    (a tenant-wide session), this behaves exactly like TenantScopedRepository — any call
    site not yet updated to pass one stays correct by default rather than leaking data.
    When set, every read is additionally filtered to that one customer's rows. Service
    functions that create a child record are expected to resolve the parent account
    through here too (not a raw session.get), so "is this account in my scope" and "what
    customer_id do I stamp on the new row" are the same lookup, not two independent ones
    that could drift."""

    def __init__(self, session: Session, tenant_id: uuid.UUID, customer_id: uuid.UUID | None = None):
        super().__init__(session, tenant_id)
        self.customer_id = customer_id

    def query(self) -> Select:
        stmt = super().query()
        if self.customer_id is not None:
            stmt = stmt.where(self.model.customer_id == self.customer_id)
        return stmt
