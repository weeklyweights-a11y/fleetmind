"""Map pipeline processing statuses to 7-layer progress for WebSocket NOTIFY."""

from __future__ import annotations

TOTAL_LAYERS = 7

_STATUS_LAYER: dict[str, int] = {
    "queued": 0,
    "parsing": 1,
    "layout": 2,
    "extracting": 3,
    "normalizing": 4,
    "validating": 5,
    "correcting": 6,
    "saving": 7,
    "complete": 7,
    "needs_review": 7,
    "failed": 7,
}


def layer_for_status(status: str) -> int:
    return _STATUS_LAYER.get(status, 0)


def progress_payload(status: str) -> dict[str, int]:
    layer = layer_for_status(status)
    return {"current_layer": layer, "total_layers": TOTAL_LAYERS}
