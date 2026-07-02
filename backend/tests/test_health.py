import pytest


@pytest.mark.asyncio
async def test_health_returns_200(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert "postgres" in data
    assert "redis" in data
    assert "neo4j" in data
