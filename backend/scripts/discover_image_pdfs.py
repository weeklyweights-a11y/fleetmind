#!/usr/bin/env python3
"""Discover document types for image PDFs 064-068."""

from __future__ import annotations

from pathlib import Path

import fitz

from app.config import settings


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
        lines.append(
            f"- **{name}**: pages={len(doc)}, extracted_chars={text_len}, likely image_pdf=True\n"
        )
        doc.close()

    content = "\n".join(lines)
    out_candidates = [
        Path(__file__).resolve().parents[2] / "docs" / "image_pdf_discovery.md",
        Path("/app/docs/image_pdf_discovery.md"),
    ]
    for out in out_candidates:
        if out.parent.exists():
            out.write_text(content, encoding="utf-8")
            print(f"Wrote {out}")
            return
    print(content)


if __name__ == "__main__":
    main()
