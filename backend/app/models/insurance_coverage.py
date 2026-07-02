import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, StandardColumnsMixin


class InsuranceCoverage(Base, StandardColumnsMixin):
    __tablename__ = "insurance_coverages"
    __table_args__ = (
        Index("ix_insurance_coverages_truck_id_expiry_date", "truck_id", "expiry_date"),
        Index("ix_insurance_coverages_policy_number", "policy_number"),
    )

    truck_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trucks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    policy_number: Mapped[str] = mapped_column(String(50), nullable=False)
    insurer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    insurer_vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    agent_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    agent_vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    coverage_type: Mapped[str] = mapped_column(String(100), nullable=False)
    liability_limit: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    cargo_limit: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    naic_number: Mapped[str | None] = mapped_column(String(10), nullable=True)
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
