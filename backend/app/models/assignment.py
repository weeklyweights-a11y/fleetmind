import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, StandardColumnsMixin


class Assignment(Base, StandardColumnsMixin):
    __tablename__ = "assignments"
    __table_args__ = (
        Index("ix_assignments_truck_id_end_date", "truck_id", "end_date"),
        Index("ix_assignments_driver_id_end_date", "driver_id", "end_date"),
        Index("ix_assignments_start_date_end_date", "start_date", "end_date"),
    )

    truck_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trucks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    driver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("drivers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    trailer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trailers.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    assignment_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="primary")
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False, server_default="1.0")
