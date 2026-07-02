#!/usr/bin/env python3
"""Bulk import Sunflower PDFs in processing waves."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import settings  # noqa: E402
from app.extraction.classifier import classify_for_bulk_import  # noqa: E402
from app.extraction.layer1_reader import read_document  # noqa: E402


API_URL = "http://localhost:8000"


def _wave_for_file(path: Path) -> int:
    reading = read_document(str(path))
    return classify_for_bulk_import(str(path), reading)


async def _upload(path: Path, client: httpx.AsyncClient) -> str:
    with path.open("rb") as f:
        resp = await client.post(
            f"{API_URL}/api/documents/upload",
            files={"file": (path.name, f, "application/pdf")},
        )
    resp.raise_for_status()
    return resp.json()["document_id"]


async def _wait_wave(doc_ids: list[str], client: httpx.AsyncClient) -> None:
    pending = set(doc_ids)
    while pending:
        for doc_id in list(pending):
            resp = await client.get(f"{API_URL}/api/documents/{doc_id}")
            status = resp.json().get("processing_status")
            if status in ("complete", "failed", "needs_review"):
                pending.discard(doc_id)
        if pending:
            await asyncio.sleep(2)


async def main() -> None:
    dataset = Path(settings.sunflower_dataset_path)
    pdfs = sorted(dataset.glob("*.pdf"))
    print(f"Found {len(pdfs)} PDFs in {dataset}")

    waves: dict[int, list[Path]] = {1: [], 2: [], 3: [], 4: []}
    for pdf in pdfs:
        waves[_wave_for_file(pdf)].append(pdf)

    async with httpx.AsyncClient(timeout=120.0) as client:
        for wave_num in (1, 2, 3, 4):
            files = waves[wave_num]
            print(f"Wave {wave_num}: uploading {len(files)} documents")
            doc_ids: list[str] = []
            for pdf in files:
                doc_id = await _upload(pdf, client)
                doc_ids.append(doc_id)
                print(f"  queued {pdf.name} -> {doc_id}")
            if doc_ids:
                print(f"  waiting for wave {wave_num} to finish...")
                await _wait_wave(doc_ids, client)
            time.sleep(1)

    print("Bulk import complete.")


if __name__ == "__main__":
    asyncio.run(main())
