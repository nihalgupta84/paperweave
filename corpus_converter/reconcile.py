"""Reconciliation of raw MinerU parser artifacts with manifest document entries."""

from __future__ import annotations

import logging
from contextlib import suppress
from pathlib import Path

from .hashing import sha256_file
from .manifest import load_manifest, save_manifest, update_stage

logger = logging.getLogger(__name__)


def reconcile_mineru(corpus: Path) -> dict[str, int]:
    """Inspect raw MinerU outputs and update the manifest stage records accordingly."""
    raw_dir = corpus / "raw" / "mineru"
    if not raw_dir.exists() and (corpus / "mineru_raw").exists():
        raw_dir = corpus / "mineru_raw"

    records = load_manifest(corpus)
    counts = {"complete": 0, "failed": 0, "pending": 0, "skipped": 0}
    roots_by_stem = {path.name: path for path in raw_dir.iterdir() if path.is_dir()} if raw_dir.exists() else {}
    roots_by_hash = {}

    for origin in raw_dir.glob("*/auto/*_origin.pdf") if raw_dir.exists() else []:
        with suppress(OSError):
            roots_by_hash[sha256_file(origin)] = origin.parents[1]

    for record in records:
        if not record.get("selected_for_extraction") or record.get("format") != "pdf":
            counts["skipped"] += 1
            continue
        root = roots_by_stem.get(Path(record["canonical_path"]).stem) or roots_by_hash.get(record["sha256"])
        markdown = list((root / "auto").glob("*.md")) if root and (root / "auto").exists() else []
        if markdown:
            update_stage(record, "mineru", "complete", raw_directory=str(root))
            counts["complete"] += 1
        elif root:
            update_stage(record, "mineru", "failed", error="No MinerU Markdown output found")
            counts["failed"] += 1
        else:
            counts["pending"] += 1

    save_manifest(corpus, records)
    logger.debug("MinerU reconciliation finished: %s", counts)
    return counts
