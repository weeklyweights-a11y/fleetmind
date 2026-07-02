"""Layer 6: Agentic correction on validation failures."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings
from app.extraction.layer4_normalizer import normalize_fields
from app.extraction.layer5_validator import validate_fields
from app.extraction.types import CorrectionAttempt, ValidationResult
from app.services.gemini_client import generate_text

logger = logging.getLogger(__name__)


async def correct_fields(
    document_type: str,
    fields: dict[str, Any],
    validation: ValidationResult,
    field_confidences: dict[str, float],
    raw_text_snippet: str,
    l1_confidence: float,
) -> tuple[dict[str, Any], list[CorrectionAttempt]]:
    if not validation.failed_fields:
        return fields, []

    corrected = dict(fields)
    attempts: list[CorrectionAttempt] = []

    for field_name in validation.failed_fields:
        for attempt in range(settings.max_correction_attempts_per_field):
            prompt = (
                f"Document type: {document_type}. Field '{field_name}' failed validation. "
                f"Current value: {corrected.get(field_name)}. "
                f"Validation: {validation.field_results.get(field_name)}. "
                f"Context: {raw_text_snippet[:1500]}. "
                f"Return only the corrected value for {field_name} as plain text."
            )
            try:
                proposed_raw = await generate_text(prompt)
                proposed = proposed_raw.strip().strip('"')
                trial = dict(corrected)
                trial[field_name] = proposed
                normalized, _ = normalize_fields(trial)
                revalidation = validate_fields(
                    document_type, normalized, field_confidences, l1_confidence
                )
                accepted = field_name not in revalidation.failed_fields
                attempts.append(
                    CorrectionAttempt(field_name, str(corrected.get(field_name)), proposed, accepted)
                )
                if accepted:
                    corrected = normalized
                    break
            except Exception as exc:
                logger.warning("L6 correction failed for %s: %s", field_name, exc)
                attempts.append(
                    CorrectionAttempt(
                        field_name, str(corrected.get(field_name)), "", False
                    )
                )
                break

    return corrected, attempts
