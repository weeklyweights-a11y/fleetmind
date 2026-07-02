import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, StandardColumnsMixin


class Truck(Base, StandardColumnsMixin):
    __tablename__ = "trucks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "unit_number", name="uq_trucks_tenant_unit_number"),
        UniqueConstraint("tenant_id", "vin", name="uq_trucks_tenant_vin"),
        Index("ix_trucks_unit_number", "unit_number"),
        Index("ix_trucks_vin", "vin"),
        Index("ix_trucks_status", "status"),
        Index("ix_trucks_acquired_date", "acquired_date"),
    )

    unit_number: Mapped[int] = mapped_column(Integer, nullable=False)
    vin: Mapped[str] = mapped_column(String(17), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    make: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    body_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fuel_type: Mapped[str | None] = mapped_column(String(30), nullable=True, server_default="Diesel")
    gross_vehicle_weight: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    acquired_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    acquired_from_vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    initial_odometer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    disposed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    disposed_to: Mapped[str | None] = mapped_column(String(200), nullable=True)
    disposal_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
