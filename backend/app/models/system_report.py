from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, StandardColumnsMixin


class SystemReport(Base, StandardColumnsMixin):
    __tablename__ = "system_reports"

    report_type: Mapped[str] = mapped_column(String(50), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict | list] = mapped_column(JSONB, nullable=False)
