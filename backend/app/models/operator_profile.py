from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, StandardColumnsMixin


class OperatorProfile(Base, StandardColumnsMixin):
    __tablename__ = "operator_profiles"
    __table_args__ = (UniqueConstraint("tenant_id", "operator_name", name="uq_operator_profiles_tenant_operator_name"),)

    operator_name: Mapped[str] = mapped_column(String(100), nullable=False)
    frequent_entities: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    frequent_topics: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    preferred_response_style: Mapped[str | None] = mapped_column(String(50), nullable=True)
    typical_session_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_conversations: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_active: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
