"""Layer 1: Physical reading with PyMuPDF."""

from __future__ import annotations

from pathlib import Path

import fitz

from app.enums import SourceFormat
from app.extraction.text_utils import meaningful_char_count
from app.extraction.types import PositionedBlock, ReadingResult


def read_document(file_path: str) -> ReadingResult:
    path = Path(file_path)
    doc = fitz.open(path)
    pages_text: list[str] = []
    positioned_blocks: list[PositionedBlock] = []
    page_images: list = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_text = page.get_text()
        pages_text.append(page_text)

        raw = page.get_text("dict")
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                line_text = "".join(s.get("text", "") for s in spans)
                if line_text.strip():
                    positioned_blocks.append(
                        PositionedBlock(
                            page=page_idx,
                            text=line_text,
                            bbox=tuple(block.get("bbox", (0, 0, 0, 0))),
                        )
                    )

    full_text = "\n".join(pages_text)
    mcount = meaningful_char_count(full_text)
    page_count = len(doc)

    if mcount > 100:
        source_format = SourceFormat.TEXT_PDF.value
        parse_method = "docling_fast"
        parse_confidence = min(1.0, mcount / max(page_count * 200, 1))
    else:
        source_format = SourceFormat.IMAGE_PDF.value
        parse_method = "image_pdf"
        parse_confidence = 0.5
        for page_idx in range(len(doc)):
            pix = doc[page_idx].get_pixmap(dpi=300)
            page_images.append(pix.pil_image())

    doc.close()

    return ReadingResult(
        source_format=source_format,
        page_count=page_count,
        full_text=full_text,
        positioned_blocks=positioned_blocks,
        page_images=page_images,
        parse_confidence=parse_confidence,
        parse_method=parse_method,
    )
