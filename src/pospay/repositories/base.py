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
