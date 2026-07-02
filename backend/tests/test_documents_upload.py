import io
import uuid

import pytest


@pytest.mark.asyncio
async def test_upload_creates_document_and_queue_job(client, tmp_path, monkeypatch):
    monkeypatch.setenv("DOCUMENT_STORAGE_PATH", str(tmp_path))

    from importlib import reload

    import app.config as config_module

    reload(config_module)

    list_response = await client.get("/api/documents")
    assert list_response.status_code == 200
    list_data = list_response.json()
    assert list_data["limit"] == 50
    assert list_data["offset"] == 0

    pdf_content = b"%PDF-1.4 test content"
    files = {"file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")}
    response = await client.post("/api/documents/upload", files=files)

    assert response.status_code == 200
    data = response.json()
    assert "document_id" in data
    assert data["status"] == "queued"
    uuid.UUID(data["document_id"])

    get_response = await client.get(f"/api/documents/{data['document_id']}")
    assert get_response.status_code == 200
    assert get_response.json()["processing_status"] == "queued"
