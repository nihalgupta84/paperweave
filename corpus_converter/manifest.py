"""Manifest loading, stage tracking, and atomic persistence for corpus documents."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io import read_jsonl, write_jsonl

logger = logging.getLogger(__name__)


def now() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def manifest_path(corpus: Path) -> Path:
    """Return canonical path to documents.jsonl in the corpus."""
    return corpus / "manifests" / "documents.jsonl"


def load_manifest(corpus: Path) -> list[dict[str, Any]]:
    """Load and normalize document records from the corpus manifest."""
    records = read_jsonl(manifest_path(corpus))
    for record in records:
        canonical = record.get("canonical_path") or record.get("pdf_path") or record.get("target_path")
        if canonical:
            record.setdefault("canonical_path", canonical)
            suffix = Path(canonical).suffix.lower()
            record.setdefault("format", "html" if suffix in {".html", ".htm"} else suffix.lstrip(".") or "pdf")
        record.setdefault("format", "pdf")
        record.setdefault("selected_for_extraction", True)
        record.setdefault("extractable", True)
        record.setdefault("selection_reason", "legacy_selected")
        stages = record.setdefault("stages", {})
        if record.get("normalization_status") == "complete":
            stages.setdefault("normalization", {"status": "complete", "updated_at": record.get("updated_at", now())})
    return records


def save_manifest(corpus: Path, records: list[dict[str, Any]]) -> None:
    """Atomically save document records to the corpus manifest."""
    sorted_records = sorted(records, key=lambda item: item.get("document_id", ""))
    target = manifest_path(corpus)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write pattern using temp file in same directory
    temp_file = target.with_name(f".{target.name}.tmp")
    write_jsonl(temp_file, sorted_records)
    temp_file.replace(target)


def update_stage(
    record: dict[str, Any],
    stage: str,
    status: str,
    **details: Any,
) -> None:
    """Update execution stage status and details on a manifest record."""
    stages = record.setdefault("stages", {})
    value = stages.setdefault(stage, {})
    value.update({"status": status, "updated_at": now(), **details})
    # Compatibility fields used by earlier workspaces.
    if stage == "mineru":
        record["mineru_status"] = status
    elif stage == "normalization":
        record["normalization_status"] = status


def record_error(record: dict[str, Any], stage: str, error: Exception | str) -> None:
    """Record a failure error for a specific processing stage."""
    update_stage(record, stage, "failed", error=str(error))
