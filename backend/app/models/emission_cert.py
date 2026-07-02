import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, StandardColumnsMixin


class EmissionCert(Base, StandardColumnsMixin):
    __tablename__ = "emission_certs"

    truck_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trucks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    test_date: Mapped[date] = mapped_column(Date, nullable=False)
    result: Mapped[str] = mapped_column(String(10), nullable=False)
    next_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    testing_facility: Mapped[str | None] = mapped_column(String(200), nullable=True)
    certificate_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
