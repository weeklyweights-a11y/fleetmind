
from sqlalchemy import Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, StandardColumnsMixin


class Vendor(Base, StandardColumnsMixin):
    __tablename__ = "vendors"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", "address", name="uq_vendors_tenant_name_address"),
        Index("ix_vendors_name", "name"),
        Index("ix_vendors_vendor_type", "vendor_type"),
        Index("ix_vendors_state", "state"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    vendor_type: Mapped[str] = mapped_column(String(50), nullable=False)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
