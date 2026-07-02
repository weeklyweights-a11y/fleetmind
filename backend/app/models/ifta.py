import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, StandardColumnsMixin


class IFTAFiling(Base, StandardColumnsMixin):
    __tablename__ = "ifta_filings"
    __table_args__ = (
        Index("ix_ifta_filings_quarter", "quarter"),
        UniqueConstraint("tenant_id", "quarter", name="uq_ifta_filings_tenant_quarter"),
    )

    ifta_account_number: Mapped[str] = mapped_column(String(50), nullable=False)
    quarter: Mapped[str] = mapped_column(String(10), nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_fleet_miles: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_fleet_gallons: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tax_due: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    penalty: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, server_default="0")
    interest: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, server_default="0")
    balance_due: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    average_fleet_mpg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )


class IFTAJurisdictionDetail(Base, StandardColumnsMixin):
    __tablename__ = "ifta_jurisdiction_details"
    __table_args__ = (Index("ix_ifta_jurisdiction_details_filing_id_jurisdiction", "filing_id", "jurisdiction"),)

    filing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ifta_filings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    jurisdiction: Mapped[str] = mapped_column(String(100), nullable=False)
    miles: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gallons: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    taxable_gallons: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    tax_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    tax_due: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    surcharge: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)


class IFTAVehicleDetail(Base, StandardColumnsMixin):
    __tablename__ = "ifta_vehicle_details"
    __table_args__ = (Index("ix_ifta_vehicle_details_filing_id_truck_id", "filing_id", "truck_id"),)

    filing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ifta_filings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    truck_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trucks.id", ondelete="RESTRICT"),
        nullable=True,
    )
    vin: Mapped[str] = mapped_column(String(17), nullable=False)
    miles: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gallons: Mapped[int | None] = mapped_column(Integer, nullable=True)
