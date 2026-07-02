import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, StandardColumnsMixin


class Registration(Base, StandardColumnsMixin):
    __tablename__ = "registrations"
    __table_args__ = (
        Index("ix_registrations_truck_id_expiry_date", "truck_id", "expiry_date"),
        Index("ix_registrations_truck_id_effective_date", "truck_id", "effective_date"),
        Index("ix_registrations_plate_number", "plate_number"),
    )

    truck_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trucks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    registration_type: Mapped[str] = mapped_column(String(30), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    registration_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    plate_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    plate_state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    registered_weight: Mapped[int | None] = mapped_column(Integer, nullable=True)
    registration_class: Mapped[str | None] = mapped_column(String(50), nullable=True)
    irp_account_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    validation_decal_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    registration_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    property_tax: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    irp_apportioned_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    title_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    total_fees_paid: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
