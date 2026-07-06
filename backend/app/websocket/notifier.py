import asyncio
import json
import logging

import asyncpg

from app.config import settings
from app.redis_client import get_all_ws_subscriptions
from app.websocket.delta_engine import push_deltas_for_event
from app.websocket.events import build_document_status_message
from app.websocket.manager import ws_manager

logger = logging.getLogger(__name__)


async def _route_notification(payload: dict) -> None:
    status = payload.get("status")
    document_id = payload.get("document_id")
    if not status or not document_id:
        logger.warning("Ignoring NOTIFY payload missing status/document_id: %s", payload)
        return

    topic = f"document:{document_id}"
    status_topic = f"document_status:{status}"
    message = build_document_status_message(payload)

    subscriptions = await get_all_ws_subscriptions()
    targets: list[str] = []
    for connection_id, topics in subscriptions.items():
        if topic in topics or status_topic in topics or "document_status" in topics:
            targets.append(connection_id)

    if targets:
        await ws_manager.broadcast(targets, message)

    terminal = status in {"complete", "needs_review", "failed"}
    review_event = payload.get("event_type") == "review"
    if terminal or review_event:
        try:
            await push_deltas_for_event(payload)
        except Exception:
            logger.exception("Delta push failed for document %s", document_id)


async def run_notify_listener(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        conn: asyncpg.Connection | None = None
        try:
            conn = await asyncpg.connect(settings.database_url.replace("+asyncpg", ""))
            queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

            def doc_callback(_connection, _pid, _channel, payload):
                queue.put_nowait(("document_events", payload))

            def intel_callback(_connection, _pid, _channel, payload):
                queue.put_nowait(("intelligence_events", payload))

            await conn.add_listener("document_events", doc_callback)
            await conn.add_listener("intelligence_events", intel_callback)
            logger.info("NOTIFY listeners started on document_events and intelligence_events")

            while not stop_event.is_set():
                try:
                    channel, payload_raw = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                try:
                    payload = json.loads(payload_raw)
                except json.JSONDecodeError:
                    logger.warning("Invalid NOTIFY JSON: %s", payload_raw)
                    continue
                if channel == "intelligence_events" and payload.get("type") == "anomalies_updated":
                    await push_deltas_for_event({"status": "complete", "type": "anomalies_updated"})
                else:
                    await _route_notification(payload)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("NOTIFY listener error; retrying in 5s")
            await asyncio.sleep(5)
        finally:
            if conn is not None:
                await conn.close()
