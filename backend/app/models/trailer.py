
from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, StandardColumnsMixin


class Trailer(Base, StandardColumnsMixin):
    __tablename__ = "trailers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "trailer_number", name="uq_trailers_tenant_trailer_number"),
        UniqueConstraint("tenant_id", "vin", name="uq_trailers_tenant_vin"),
    )

    trailer_number: Mapped[str] = mapped_column(String(20), nullable=False)
    vin: Mapped[str | None] = mapped_column(String(17), nullable=True)
    type_: Mapped[str | None] = mapped_column("type", String(50), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    make: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
