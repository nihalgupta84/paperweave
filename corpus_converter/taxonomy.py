"""Taxonomy loading, faceted document classification, and collection index generation."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .io import read_json, read_jsonl, write_json
from .manifest import load_manifest, save_manifest, update_stage
from .semantic import evidence
from .validation import validate_taxonomy

logger = logging.getLogger(__name__)


def find_taxonomy_file(root: Path, relative_name: str) -> Path:
    """Find a taxonomy json file either in root, root/taxonomies, or relative to current working directory."""
    candidates = [
        root / "taxonomies" / f"{relative_name}.json",
        root / f"{relative_name}.json",
        Path.cwd() / "taxonomies" / f"{relative_name}.json",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return root / "taxonomies" / f"{relative_name}.json"


def load_taxonomy(root: Path, profile: str | None) -> dict[str, dict[str, list[str]]]:
    """Load core taxonomy and optionally merge an extension domain profile."""
    sources = [find_taxonomy_file(root, "core")]
    if profile and profile != "core":
        sources.append(find_taxonomy_file(root, profile))

    merged: dict[str, dict[str, list[str]]] = defaultdict(dict)
    for source in sources:
        value = read_json(source, {})
        if not value:
            raise FileNotFoundError(f"Taxonomy not found or invalid: {source}")
        for facet, labels in value.items():
            merged[facet].update(labels)
    return dict(merged)


def term_present(term: str, text: str) -> bool:
    """Check whether a taxonomy alias keyword appears as a standalone word in text."""
    return bool(re.search(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", text, re.I))


def classify_document(blocks: list[dict[str, Any]], taxonomy: dict[str, dict[str, list[str]]]) -> dict[str, Any]:
    """Match taxonomy facet terms against document blocks and extract up to 3 evidence citations per match."""
    assignments: dict[str, list[dict[str, Any]]] = {}
    for facet, labels in taxonomy.items():
        facet_values = []
        for label_id, aliases in labels.items():
            matches = []
            for block in blocks:
                text = block.get("text", "")
                matched = next((alias for alias in aliases if term_present(alias, text)), None)
                if matched:
                    matches.append(evidence(block))
                    if len(matches) == 3:
                        break
            if matches:
                facet_values.append(
                    {
                        "id": label_id,
                        "name": label_id.rsplit(".", 1)[-1].replace("_", " ").title(),
                        "status": "accepted",
                        "source": "deterministic_alias_match",
                        "evidence": matches,
                    }
                )
        assignments[facet] = facet_values
    return assignments


def classify_corpus(corpus: Path, project_root: Path, profile: str | None) -> dict[str, int]:
    """Classify all works in the corpus using the resolved taxonomy profile."""
    taxonomy = load_taxonomy(project_root, profile)
    count = 0
    manifest = load_manifest(corpus)
    records_by_id = {record["document_id"]: record for record in manifest}

    for record_dir in sorted((corpus / "records").glob("work_*")):
        work = read_json(record_dir / "work.json", {})
        if not work:
            continue
        blocks = []
        for document_id in work["document_ids"]:
            blocks.extend(read_jsonl(corpus / "papers" / document_id / "sections.jsonl"))
        output = {
            "schema_version": "1.0",
            "work_id": work["work_id"],
            "profile": profile or "core",
            "facets": classify_document(blocks, taxonomy),
        }
        validate_taxonomy(output)
        write_json(record_dir / "taxonomy.json", output)
        for document_id in work["document_ids"]:
            if document_id in records_by_id:
                update_stage(records_by_id[document_id], "taxonomy", "complete", profile=profile or "core")
        count += 1

    if manifest:
        save_manifest(corpus, manifest)
    logger.info("Classified %d works under profile '%s'", count, profile or "core")
    return {"documents": count}


def generate_collections(corpus: Path) -> dict[str, int]:
    """Generate multi-facet Markdown collection indexes."""
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record_dir in sorted((corpus / "records").glob("work_*")):
        work = read_json(record_dir / "work.json", {})
        taxonomy = read_json(record_dir / "taxonomy.json", {})
        for facet, assignments in taxonomy.get("facets", {}).items():
            for assignment in assignments:
                grouped[(facet, assignment["id"])].append(work)

    for (facet, label_id), works in grouped.items():
        path = corpus / "collections" / f"by_{facet}" / f"{label_id.replace('.', '_')}.md"
        lines = [f"# {label_id.rsplit('.', 1)[-1].replace('_', ' ').title()}", ""]
        for work in sorted(works, key=lambda item: item.get("title", "")):
            lines.append(f"- **{work.get('title', work['work_id'])}** — `{work['work_id']}`")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    logger.info("Generated %d collection index files", len(grouped))
    return {"collections": len(grouped)}
