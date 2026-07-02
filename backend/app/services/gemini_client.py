"""Gemini API client."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


def _get_model():
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    return genai.GenerativeModel(settings.gemini_model_name)


async def generate_text(prompt: str) -> str:
    model = _get_model()
    response = await model.generate_content_async(prompt)
    return response.text or ""


async def generate_json_from_images(images: list[Any], prompt: str) -> dict | str:
    model = _get_model()
    parts: list[Any] = [prompt]
    parts.extend(images)
    response = await model.generate_content_async(
        parts,
        generation_config={"response_mime_type": "application/json"},
    )
    text = response.text or "{}"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text
