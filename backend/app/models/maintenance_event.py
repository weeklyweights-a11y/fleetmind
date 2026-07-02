import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, StandardColumnsMixin


class MaintenanceEvent(Base, StandardColumnsMixin):
    __tablename__ = "maintenance_events"
    __table_args__ = (
        Index("ix_maintenance_events_truck_id_service_date", "truck_id", "service_date"),
        Index("ix_maintenance_events_vendor_id_service_date", "vendor_id", "service_date"),
        Index("ix_maintenance_events_category", "category"),
        Index("ix_maintenance_events_invoice_number", "invoice_number"),
    )

    truck_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trucks.id", ondelete="RESTRICT"),
        nullable=False,
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=False,
    )
    service_date: Mapped[date] = mapped_column(Date, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    parts_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    labor_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    sales_tax: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, server_default="0.00")
    payment_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="unknown")
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    technician_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False)
    po_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    odometer_reading: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
