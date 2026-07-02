import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, StandardColumnsMixin


class Conversation(Base, StandardColumnsMixin):
    __tablename__ = "conversations"

    operator_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entities_discussed: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    topics: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    key_findings: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    unresolved_items: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class ConversationMessage(Base, StandardColumnsMixin):
    __tablename__ = "conversation_messages"
    __table_args__ = (Index("ix_conversation_messages_conversation_id_message_index", "conversation_id", "message_index"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tools_called: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    message_index: Mapped[int] = mapped_column(Integer, nullable=False)
