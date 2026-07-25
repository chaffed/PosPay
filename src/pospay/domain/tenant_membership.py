import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from pospay.db.base import Base, new_uuid


class TenantMembership(Base):
    """What actually grants a User access to a Tenant, and which SecurityGroup governs
    that access — this is the join that makes cross-tenant identities possible: one User
    row can have a TenantMembership (each with its own security group) in more than one
    Tenant. Deactivating one membership (is_active=False) only removes access to that one
    tenant, not the identity itself or its other memberships."""

    __tablename__ = "tenant_membership"
    __table_args__ = (UniqueConstraint("user_id", "tenant_id", name="uq_tenant_membership_user_tenant"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id"), nullable=False, index=True)
    security_group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("security_group.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
