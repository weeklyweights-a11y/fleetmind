#!/usr/bin/env python3
"""Discover document types for image PDFs 064-068."""

from __future__ import annotations

import sys
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import settings  # noqa: E402


def main() -> None:
    dataset = Path(settings.sunflower_dataset_path)
    targets = [f"document_{n:03d}.pdf" for n in range(64, 69)]
    lines = ["# Image PDF discovery (docs 064-068)\n"]

    for name in targets:
        path = dataset / name
        if not path.exists():
            lines.append(f"- **{name}**: not found\n")
            continue
        doc = fitz.open(path)
        text_len = sum(len(page.get_text()) for page in doc)
        lines.append(f"- **{name}**: pages={len(doc)}, extracted_chars={text_len}, likely image_pdf=True\n")
        doc.close()

    out = ROOT / "docs" / "image_pdf_discovery.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
