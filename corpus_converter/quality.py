"""Document parsing quality diagnostics and heuristic alert assessment."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .io import read_jsonl, write_json

logger = logging.getLogger(__name__)


def assess_document(paper_dir: Path) -> dict[str, Any]:
    """Evaluate text volume, block density, and headings to flag abnormal conversions."""
    blocks = read_jsonl(paper_dir / "blocks.jsonl")
    texts = [block.get("text", "") for block in blocks]
    character_count = sum(len(text.strip()) for text in texts)
    empty_count = sum(not text.strip() for text in texts)
    headings = sum(block.get("heading_level") is not None for block in blocks)
    page_values = [block.get("page_index") for block in blocks if block.get("page_index") is not None]
    reasons = []

    if character_count < 500:
        reasons.append("very_low_text")
    if len(blocks) < 3:
        reasons.append("very_few_blocks")
    if blocks and empty_count / len(blocks) > 0.5:
        reasons.append("many_empty_blocks")

    status = "review_needed" if reasons else "accepted"
    if reasons:
        logger.warning("Quality alert for %s: %s", paper_dir.name, reasons)

    quality = {
        "block_count": len(blocks),
        "character_count": character_count,
        "heading_count": headings,
        "empty_block_fraction": round(empty_count / len(blocks), 4) if blocks else 1.0,
        "page_count": max(page_values) + 1 if page_values else None,
        "ocr_used": None,
        "status": status,
        "reasons": reasons,
    }
    write_json(paper_dir / "quality.json", quality)
    return quality
