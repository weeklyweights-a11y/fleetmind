import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, StandardColumnsMixin


class Title(Base, StandardColumnsMixin):
    __tablename__ = "titles"
    __table_args__ = (
        Index("ix_titles_truck_id", "truck_id"),
        Index("ix_titles_title_number", "title_number"),
    )

    truck_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trucks.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title_number: Mapped[str] = mapped_column(String(50), nullable=False)
    title_state: Mapped[str] = mapped_column(String(2), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    vin: Mapped[str] = mapped_column(String(17), nullable=False)
    owner_name: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    lien_holder: Mapped[str | None] = mapped_column(String(200), nullable=True)
    previous_title_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    previous_title_state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    control_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    title_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
