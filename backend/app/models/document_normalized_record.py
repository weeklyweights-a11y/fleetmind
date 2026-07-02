import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, StandardColumnsMixin


class DocumentNormalizedRecord(Base, StandardColumnsMixin):
    __tablename__ = "document_normalized_records"
    __table_args__ = (
        Index("ix_document_normalized_records_document_id", "document_id"),
        Index("ix_document_normalized_records_target_table_target_record_id", "target_table", "target_record_id"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_table: Mapped[str] = mapped_column(String(50), nullable=False)
    target_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
