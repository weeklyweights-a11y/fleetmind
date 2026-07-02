#!/usr/bin/env python3
"""One-command Phase 2: reset, import all Sunflower PDFs, wait, verify.

Usage (inside api container):
  python scripts/run_phase2.py
  python scripts/run_phase2.py --skip-reset   # keep existing DB, only import missing docs
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys

import httpx
from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.models.document import Document
from app.services.pipeline_wait import wait_for_documents, wait_for_worker_idle

API_URL = "http://api:8000"


async def _bulk_import(*, skip_existing: bool = False) -> None:
    """Run bulk import logic inline (same waves as bulk_import_sunflower.py)."""
    from pathlib import Path

    from app.extraction.classifier import classify_for_bulk_import

    dataset = Path(settings.sunflower_dataset_path)
    pdfs = sorted(dataset.glob("*.pdf"))

    existing_names: set[str] = set()
    if skip_existing:
        async with async_session_factory() as db:
            rows = await db.execute(select(Document.original_filename))
            existing_names = {name for (name,) in rows.all()}
        pdfs = [pdf for pdf in pdfs if pdf.name not in existing_names]
        print(
            f"Skipping {len(existing_names)} already-imported PDF(s); "
            f"importing {len(pdfs)} remaining",
            flush=True,
        )

    print(f"Importing {len(pdfs)} PDFs from {dataset}", flush=True)

    waves: dict[int, list[Path]] = {1: [], 2: [], 3: [], 4: []}
    for pdf in pdfs:
        waves[classify_for_bulk_import(str(pdf))].append(pdf)

    all_skipped: list[str] = []
    async with httpx.AsyncClient(timeout=120.0) as client:
        for wave_num in (1, 2, 3, 4):
            files = waves[wave_num]
            if not files:
                continue
            print(f"Wave {wave_num}: uploading {len(files)} documents", flush=True)
            doc_ids: list[str] = []
            for pdf in files:
                with pdf.open("rb") as f:
                    resp = await client.post(
                        f"{API_URL}/api/documents/upload",
                        files={"file": (pdf.name, f, "application/pdf")},
                    )
                resp.raise_for_status()
                doc_id = resp.json()["document_id"]
                doc_ids.append(doc_id)
            skipped = await wait_for_documents(doc_ids, f"wave {wave_num}", api_url=API_URL)
            all_skipped.extend(skipped)

    if all_skipped:
        print(
            f"Skipped {len(all_skipped)} stuck document(s) during import "
            f"(will retry in step 3, max {settings.document_max_retries} attempts)",
            flush=True,
        )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run full Phase 2 pipeline")
    parser.add_argument(
        "--skip-reset",
        action="store_true",
        help="Do not wipe DB/Neo4j before import",
    )
    args = parser.parse_args()

    if not settings.gemini_api_key:
        print(
            "WARNING: GEMINI_API_KEY / GOOGLE_API_KEY not set — image PDFs will fail",
            flush=True,
        )

    if not args.skip_reset:
        print("=== Step 1: Reset Phase 2 data ===", flush=True)
        subprocess.run([sys.executable, "scripts/reset_phase2_data.py"], check=True)
    else:
        print("=== Step 1: Skipped reset ===", flush=True)

    print("=== Step 2: Bulk import (waves 1–4, auto-wait) ===", flush=True)
    await _bulk_import(skip_existing=args.skip_reset)

    print("=== Step 3: Re-process any stragglers ===", flush=True)
    subprocess.run([sys.executable, "scripts/reprocess_incomplete.py"], check=True)

    skipped = await wait_for_worker_idle()
    if skipped:
        print(
            f"Skipped {len(skipped)} stuck document(s) while draining worker "
            f"(max {settings.document_max_retries} retries each)",
            flush=True,
        )

    print("=== Step 4: Acceptance verification ===", flush=True)
    result = subprocess.run([sys.executable, "scripts/verify_phase2_acceptance.py"])
    sys.exit(result.returncode)


if __name__ == "__main__":
    asyncio.run(main())
