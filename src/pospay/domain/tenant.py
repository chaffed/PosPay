import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from pospay.db.base import Base, new_uuid


class Tenant(Base):
    __tablename__ = "tenant"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    require_dual_control: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stale_date_threshold_days: Mapped[int] = mapped_column(Integer, nullable=False, default=180)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Branding — local disk paths (see web/branding_storage.py), never the blob itself in
    # the row, same pattern as CheckImage.front_image_path. All nullable: unset means "use
    # the app's plain defaults" everywhere this is rendered.
    logo_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    logo_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    favicon_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    favicon_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    accent_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
