import pytest

from app.redis_client import (
    delete_ws_subscription,
    get_topic_cache,
    get_ws_subscriptions,
    merge_ws_subscriptions,
    set_topic_cache,
    set_ws_subscriptions,
)
from app.websocket.events import build_data_update_message, build_document_status_message
from app.websocket.topic_mapper import topics_for_document_event


@pytest.mark.asyncio
async def test_ws_subscription_redis_helpers():
    await set_ws_subscriptions("test-conn-1", ["document_status"])
    topics = await get_ws_subscriptions("test-conn-1")
    assert topics == ["document_status"]
    await delete_ws_subscription("test-conn-1")
    assert await get_ws_subscriptions("test-conn-1") == []


@pytest.mark.asyncio
async def test_merge_ws_subscriptions():
    await set_ws_subscriptions("test-conn-merge", ["fleet_stats"])
    merged = await merge_ws_subscriptions(
        "test-conn-merge",
        ["truck_19_maintenance", "fleet_stats"],
        ["fleet_stats"],
    )
    assert merged == ["truck_19_maintenance", "fleet_stats"]
    await delete_ws_subscription("test-conn-merge")


@pytest.mark.asyncio
async def test_topic_cache_round_trip():
    await set_topic_cache("fleet_stats", {"active": 16})
    cached = await get_topic_cache("fleet_stats")
    assert cached == {"active": 16}


def test_topic_mapper_service_invoice():
    topics = topics_for_document_event(
        {
            "status": "complete",
            "document_id": "x",
            "document_type": "service_invoice",
            "truck_unit": 19,
        }
    )
    assert "truck_19_maintenance" in topics
    assert "fleet_stats" in topics
    assert "document_status" in topics


def test_document_status_message_shape():
    msg = build_document_status_message(
        {
            "document_id": "abc",
            "status": "extracting",
            "filename": "inv.pdf",
            "progress": {"current_layer": 3, "total_layers": 7},
            "document_type": "service_invoice",
            "truck_unit": 19,
        }
    )
    assert msg["type"] == "document_status"
    assert msg["progress"]["current_layer"] == 3
    assert msg["details"]["truck_unit"] == 19


def test_data_update_message_shape():
    msg = build_data_update_message(
        "truck_19_maintenance",
        {"total_spend": {"old": 100, "new": 200}},
    )
    assert msg["type"] == "data_update"
    assert msg["topic"] == "truck_19_maintenance"
    assert "timestamp" in msg
