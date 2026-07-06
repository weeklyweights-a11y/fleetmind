"""Gemini API client."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any, TypeVar

from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

_model = None


def _get_model():
    global _model
    if _model is None:
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        _model = genai.GenerativeModel(settings.gemini_model_name)
    return _model


async def _with_retry(fn, retries: int = 1):
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return await fn()
        except Exception as exc:
            last_exc = exc
            logger.warning("Gemini call failed (attempt %s): %s", attempt + 1, exc)
            if attempt >= retries:
                raise
    raise last_exc  # type: ignore[misc]


async def generate_text(prompt: str) -> str:
    async def _call():
        model = _get_model()
        response = await model.generate_content_async(prompt)
        return response.text or ""

    return await _with_retry(_call)


async def generate_json(prompt: str) -> dict[str, Any]:
    async def _call():
        model = _get_model()
        response = await model.generate_content_async(
            prompt,
            generation_config={"response_mime_type": "application/json"},
        )
        text = response.text or "{}"
        return json.loads(text)

    return await _with_retry(_call)


async def stream_text(prompt: str) -> AsyncIterator[str]:
    model = _get_model()
    response = await model.generate_content_async(prompt, stream=True)
    previous = ""
    async for chunk in response:
        text = chunk.text or ""
        if not text:
            continue
        if text.startswith(previous):
            delta = text[len(previous) :]
            previous = text
        else:
            delta = text
            previous += text
        if delta:
            yield delta


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
