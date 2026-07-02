import pytest

from app.redis_client import (
    delete_ws_subscription,
    get_ws_subscriptions,
    merge_ws_subscriptions,
    set_ws_subscriptions,
)


@pytest.mark.asyncio
async def test_ws_subscription_redis_helpers():
    await set_ws_subscriptions("test-conn-1", ["document_status"])
    topics = await get_ws_subscriptions("test-conn-1")
    assert topics == ["document_status"]
    await delete_ws_subscription("test-conn-1")
    assert await get_ws_subscriptions("test-conn-1") == []


@pytest.mark.asyncio
async def test_merge_subscribe_adds_topics():
    await merge_ws_subscriptions("test-conn-2", ["a"], [])
    merged = await merge_ws_subscriptions("test-conn-2", ["b"], [])
    assert merged == ["a", "b"]
    await delete_ws_subscription("test-conn-2")
