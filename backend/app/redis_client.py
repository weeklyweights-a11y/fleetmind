import json
import logging
from typing import Any

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)

DOCUMENT_PROCESSING_QUEUE = "document_processing"
DOCUMENT_PROCESSING_DLQ = "document_processing:dlq"
WS_SUBSCRIPTIONS_HASH = "ws_subscriptions"
TOPIC_CACHE_PREFIX = "topic_cache:"
CHAT_SESSION_PREFIX = "chat_sessions:"

_redis: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def ping_redis() -> bool:
    try:
        return (await get_redis().ping()) is True
    except Exception:
        logger.exception("Redis ping failed")
        return False


async def set_ws_subscriptions(connection_id: str, topics: list[str]) -> None:
    await get_redis().hset(WS_SUBSCRIPTIONS_HASH, connection_id, json.dumps(list(dict.fromkeys(topics))))


async def merge_ws_subscriptions(connection_id: str, add: list[str], remove: list[str] | None = None) -> list[str]:
    current = await get_ws_subscriptions(connection_id)
    remove_set = set(remove or [])
    merged = [t for t in current if t not in remove_set]
    for topic in add:
        if topic not in merged:
            merged.append(topic)
    await set_ws_subscriptions(connection_id, merged)
    return merged


async def get_ws_subscriptions(connection_id: str) -> list[str]:
    raw = await get_redis().hget(WS_SUBSCRIPTIONS_HASH, connection_id)
    if not raw:
        return []
    return json.loads(raw)


async def delete_ws_subscription(connection_id: str) -> None:
    await get_redis().hdel(WS_SUBSCRIPTIONS_HASH, connection_id)


async def get_all_ws_subscriptions() -> dict[str, list[str]]:
    raw = await get_redis().hgetall(WS_SUBSCRIPTIONS_HASH)
    return {k: json.loads(v) for k, v in raw.items()}


async def get_subscribers_for_topics(topics: list[str]) -> list[str]:
    topic_set = set(topics)
    targets: list[str] = []
    for connection_id, subscribed in (await get_all_ws_subscriptions()).items():
        if topic_set.intersection(subscribed):
            targets.append(connection_id)
    return targets


async def get_topic_cache(topic: str) -> dict[str, Any] | None:
    raw = await get_redis().get(f"{TOPIC_CACHE_PREFIX}{topic}")
    if not raw:
        return None
    return json.loads(raw)


async def set_topic_cache(topic: str, data: dict[str, Any]) -> None:
    await get_redis().set(f"{TOPIC_CACHE_PREFIX}{topic}", json.dumps(data))


async def get_chat_session(conversation_id: str) -> dict[str, Any] | None:
    raw = await get_redis().get(f"{CHAT_SESSION_PREFIX}{conversation_id}")
    if not raw:
        return None
    return json.loads(raw)


async def set_chat_session(
    conversation_id: str,
    data: dict[str, Any],
    ttl_seconds: int = 86400,
) -> None:
    await get_redis().set(
        f"{CHAT_SESSION_PREFIX}{conversation_id}",
        json.dumps(data),
        ex=ttl_seconds,
    )


async def delete_chat_session(conversation_id: str) -> None:
    await get_redis().delete(f"{CHAT_SESSION_PREFIX}{conversation_id}")
