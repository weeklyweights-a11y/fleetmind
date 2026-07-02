"""Phase 3 API smoke tests."""

import pytest


@pytest.mark.asyncio
async def test_trucks_list(client):
    r = await client.get("/api/trucks?page=1&per_page=5")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "total_pages" in data


@pytest.mark.asyncio
async def test_fleet_overview(client):
    r = await client.get("/api/fleet/overview")
    assert r.status_code == 200
    assert "fleet_composition" in r.json()


@pytest.mark.asyncio
async def test_truck_not_found(client):
    r = await client.get("/api/trucks/99999")
    assert r.status_code == 404
    assert r.json()["error_code"] == "TRUCK_NOT_FOUND"


@pytest.mark.asyncio
async def test_compliance_matrix(client):
    r = await client.get("/api/compliance/matrix")
    assert r.status_code == 200
    assert "matrix" in r.json()


@pytest.mark.asyncio
async def test_anomalies_empty(client):
    r = await client.get("/api/anomalies")
    assert r.status_code == 200
    assert r.json()["anomalies"] == []


@pytest.mark.asyncio
async def test_memory_search_empty(client):
    r = await client.get("/api/conversations/search?q=test")
    assert r.status_code == 200
    assert r.json()["matching_conversations"] == []
