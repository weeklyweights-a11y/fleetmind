from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, StandardColumnsMixin


class BackgroundJobRun(Base, StandardColumnsMixin):
    __tablename__ = "background_job_runs"

    process_name: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entities_processed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    anomalies_created: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    anomalies_updated: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    anomalies_resolved: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    details: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
