#!/usr/bin/env python3
"""Bulk import Sunflower PDFs in processing waves."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import httpx

from app.config import settings
from app.extraction.classifier import classify_for_bulk_import
from app.extraction.layer1_reader import read_document
from app.services.pipeline_wait import wait_for_documents

API_URL = "http://api:8000"


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


async def main() -> None:
    dataset = Path(settings.sunflower_dataset_path)
    pdfs = sorted(dataset.glob("*.pdf"))
    print(f"Found {len(pdfs)} PDFs in {dataset}", flush=True)

    waves: dict[int, list[Path]] = {1: [], 2: [], 3: [], 4: []}
    for pdf in pdfs:
        waves[_wave_for_file(pdf)].append(pdf)

    async with httpx.AsyncClient(timeout=120.0) as client:
        for wave_num in (1, 2, 3, 4):
            files = waves[wave_num]
            print(f"Wave {wave_num}: uploading {len(files)} documents", flush=True)
            doc_ids: list[str] = []
            for pdf in files:
                doc_id = await _upload(pdf, client)
                doc_ids.append(doc_id)
                print(f"  queued {pdf.name} -> {doc_id}", flush=True)
            if doc_ids:
                print(f"  waiting for wave {wave_num} to finish...", flush=True)
                skipped = await wait_for_documents(doc_ids, f"wave {wave_num}", api_url=API_URL)
                if skipped:
                    print(f"  skipped {len(skipped)} stuck document(s) in wave {wave_num}", flush=True)
            time.sleep(1)

    print("Bulk import complete.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
