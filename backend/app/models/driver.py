from datetime import date

from sqlalchemy import Date, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, StandardColumnsMixin


class Driver(Base, StandardColumnsMixin):
    __tablename__ = "drivers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "driver_code", name="uq_drivers_tenant_driver_code"),
        Index("ix_drivers_driver_code", "driver_code"),
        Index("ix_drivers_license_number", "license_number"),
        Index("ix_drivers_license_expiry_date", "license_expiry_date"),
        Index("ix_drivers_status", "status"),
        Index("ix_drivers_full_name", "full_name"),
    )

    driver_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    sex: Mapped[str | None] = mapped_column(String(1), nullable=True)
    height: Mapped[str | None] = mapped_column(String(10), nullable=True)
    weight_lbs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    eye_color: Mapped[str | None] = mapped_column(String(10), nullable=True)
    license_number: Mapped[str] = mapped_column(String(30), nullable=False)
    license_state: Mapped[str] = mapped_column(String(2), nullable=False, server_default="KS")
    license_class: Mapped[str] = mapped_column(String(5), nullable=False)
    license_endorsements: Mapped[str | None] = mapped_column(String(30), nullable=True)
    license_restrictions: Mapped[str | None] = mapped_column(String(50), nullable=True)
    license_issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    license_expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    medical_cert_expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
