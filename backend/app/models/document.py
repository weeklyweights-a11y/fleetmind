import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, StandardColumnsMixin


class Document(Base, StandardColumnsMixin):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_document_type", "document_type"),
        Index("ix_documents_processing_status", "processing_status"),
        Index("ix_documents_truck_id_document_type", "truck_id", "document_type"),
        Index("ix_documents_driver_id", "driver_id"),
        Index("ix_documents_vendor_id", "vendor_id"),
        Index("ix_documents_document_date", "document_date"),
    )

    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_format: Mapped[str] = mapped_column(String(20), nullable=False)
    parse_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    document_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    document_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    truck_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trucks.id", ondelete="RESTRICT"),
        nullable=True,
    )
    driver_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("drivers.id", ondelete="RESTRICT"),
        nullable=True,
    )
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=True,
    )
    raw_extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="queued")
    parse_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    entity_resolution_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    review_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[str | None] = mapped_column(Text, nullable=True)
