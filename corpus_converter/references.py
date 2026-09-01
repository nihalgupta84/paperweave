"""Extraction and parsing of bibliographic references from scholarly documents."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from .io import read_jsonl, write_json

logger = logging.getLogger(__name__)


def parse_reference_line(raw: str, index: int, block: dict[str, Any]) -> dict[str, Any]:
    """Parse a single raw citation string into candidate fields."""
    raw_cleaned = re.sub(r"^\s*\[?\d+\]?[.\s]+", "", raw).strip()

    # Extract 4-digit year in parentheses or standalone
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", raw_cleaned)
    year = int(year_match.group(1)) if year_match else None

    # Guess title if wrapped in quotes or following year
    title = None
    quoted = re.search(r'["“”\'‘’]([^"“”\'‘’]+)["“”\'‘’]', raw_cleaned)
    if quoted:
        title = quoted.group(1).strip()
    elif year_match:
        after_year = raw_cleaned[year_match.end() :].lstrip(" .:,;-\t")
        parts = re.split(r"[.!?]", after_year)
        if parts and len(parts[0].strip()) > 5:
            title = parts[0].strip()

    # Author estimation: text before year or first period
    authors: list[str] = []
    if year_match:
        before_year = raw_cleaned[: year_match.start()].strip(" (.,;:-")
        if before_year:
            for piece in re.split(r"[,;]|(?:\band\b)", before_year):
                piece_clean = piece.strip()
                if 2 <= len(piece_clean) <= 60 and not piece_clean.isdigit():
                    authors.append(piece_clean)

    doi_match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", raw_cleaned, re.I)
    arxiv_match = re.search(r"\barXiv:\s*([\w.\-/]+)", raw_cleaned, re.I)

    return {
        "raw": raw,
        "index": index,
        "parsed_title": title,
        "parsed_authors": authors,
        "parsed_year": year,
        "doi": doi_match.group(0).rstrip(".,;)") if doi_match else None,
        "arxiv_id": arxiv_match.group(1) if arxiv_match else None,
        "evidence": {
            "document_id": block.get("document_id"),
            "block_id": block.get("block_id"),
            "page_index": block.get("page_index"),
            "section": " > ".join(block.get("section_path") or []),
        },
    }


def extract_references_from_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract individual reference items from document blocks."""
    ref_blocks = [
        block
        for block in blocks
        if block.get("section_role") == "references"
        or "references" in [s.lower() for s in block.get("section_path", [])]
    ]

    references = []
    current_index = 1

    for block in ref_blocks:
        text = block.get("text", "").strip()
        if not text or len(text) < 10:
            continue

        # Check if block has multiple numbered entries
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in lines:
            if len(line) >= 15:
                ref_item = parse_reference_line(line, current_index, block)
                references.append(ref_item)
                current_index += 1

    return references


def extract_and_save_references(paper_dir: Path, record_dir: Path, document_id: str) -> list[dict[str, Any]]:
    """Extract references for a document and persist to record directory."""
    blocks = read_jsonl(paper_dir / "sections.jsonl") or read_jsonl(paper_dir / "blocks.jsonl")
    references = extract_references_from_blocks(blocks)

    doc_ref_dir = record_dir / "documents" / document_id
    doc_ref_dir.mkdir(parents=True, exist_ok=True)
    write_json(doc_ref_dir / "references.json", {"document_id": document_id, "references": references})

    return references
