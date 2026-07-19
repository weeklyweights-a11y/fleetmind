"""Background conversation summary generation."""

from __future__ import annotations

import logging
import uuid


from app.chat.operator_profile import maybe_infer_response_style, update_profile_after_conversation
from app.chat.orchestrator import mark_summary_scheduled
from app.chat.prompts import load_prompt
from app.chat.session import get_messages
from app.database import async_session_factory
from app.models.conversation import Conversation
from app.services.gemini_client import generate_json, generate_text

logger = logging.getLogger(__name__)


async def generate_conversation_summary(conversation_id: uuid.UUID) -> None:
    if not mark_summary_scheduled(str(conversation_id)):
        return

    async with async_session_factory() as db:
        conv = await db.get(Conversation, conversation_id)
        if conv is None or conv.summary_text:
            return
        messages = await get_messages(db, conversation_id)
        transcript = "\n".join(f"{m.role}: {m.content}" for m in messages)
        prompt = load_prompt("conversation_summary.txt") + f"\n\nTranscript:\n{transcript}"
        summary: dict
        try:
            summary = await generate_json(prompt)
            if not isinstance(summary, dict):
                raise ValueError("invalid summary")
        except Exception:
            logger.exception("Summary LLM failed for %s", conversation_id)
            summary = {
                "entities_discussed": [],
                "topics": [],
                "key_findings": [],
                "unresolved_items": [],
                "summary_text": transcript[:2000],
            }

        conv.entities_discussed = summary.get("entities_discussed")
        conv.topics = summary.get("topics")
        conv.key_findings = summary.get("key_findings")
        conv.unresolved_items = summary.get("unresolved_items")
        conv.summary_text = summary.get("summary_text") or await generate_text(
            f"Summarize this fleet chat in one paragraph:\n{transcript[:4000]}"
        )
        operator = conv.operator_name or "default"
        await update_profile_after_conversation(db, operator, summary)
        await maybe_infer_response_style(db, operator)
        await db.commit()
