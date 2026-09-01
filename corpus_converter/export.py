"""Export corpus data to BibTeX, CSV, and JSON-LD formats."""

from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path
from typing import Any

from .io import read_json

logger = logging.getLogger(__name__)


def export_bibtex(corpus: Path, output_path: Path) -> dict[str, int]:
    """Export work records to a BibTeX bibliography file."""
    entries = []
    for record_dir in sorted((corpus / "records").glob("work_*")):
        work = read_json(record_dir / "work.json", {})
        if not work:
            continue

        work_id = work["work_id"]
        title = work.get("title", "Untitled")
        authors = work.get("authors", [])
        author_str = " and ".join(authors) if authors else "Unknown"
        year_val = str(work.get("year")) if work.get("year") else ""

        # Create a citation key like AuthorYear or work_id
        first_author = authors[0].split()[-1] if authors else "Paper"
        first_author_clean = re.sub(r"[^A-Za-z]", "", first_author)
        key = f"{first_author_clean}{year_val or work_id[-6:]}"

        entry_lines = [
            f"@article{{{key},",
            f"  title = {{{{{title}}}}},",
            f"  author = {{{author_str}}},",
        ]
        if year_val:
            entry_lines.append(f"  year = {{{year_val}}},")
        if work.get("doi"):
            entry_lines.append(f'  doi = {{{work["doi"]}}},')
        if work.get("arxiv_id"):
            entry_lines.append(f'  eprint = {{{work["arxiv_id"]}}},')
            entry_lines.append("  archivePrefix = {arXiv},")
        entry_lines.append(f"  note = {{PaperWeave Work ID: {work_id}}}")
        entry_lines.append("}\n")
        entries.append("\n".join(entry_lines))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(entries), encoding="utf-8")
    logger.info("Exported %d BibTeX entries to %s", len(entries), output_path)
    return {"exported": len(entries), "format": "bibtex", "output": str(output_path)}


def export_csv(corpus: Path, output_path: Path) -> dict[str, int]:
    """Export work records and findings to a structured CSV table."""
    rows = []
    for record_dir in sorted((corpus / "records").glob("work_*")):
        work = read_json(record_dir / "work.json", {})
        experiments = read_json(record_dir / "experiments.json", {})
        taxonomy = read_json(record_dir / "taxonomy.json", {})
        if not work:
            continue

        datasets = [d["name"] for d in experiments.get("datasets", [])]
        metrics = [m["name"] for m in experiments.get("metrics", [])]
        method_families = [m["name"] for m in taxonomy.get("facets", {}).get("method_family", [])]
        paradigms = [p["name"] for p in taxonomy.get("facets", {}).get("learning_paradigm", [])]

        rows.append(
            {
                "work_id": work["work_id"],
                "title": work.get("title", ""),
                "authors": "; ".join(work.get("authors", [])),
                "year": work.get("year", ""),
                "doi": work.get("doi", ""),
                "arxiv_id": work.get("arxiv_id", ""),
                "document_count": len(work.get("document_ids", [])),
                "datasets": "; ".join(datasets),
                "metrics": "; ".join(metrics),
                "method_families": "; ".join(method_families),
                "learning_paradigms": "; ".join(paradigms),
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        if rows:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    logger.info("Exported %d rows to CSV at %s", len(rows), output_path)
    return {"exported": len(rows), "format": "csv", "output": str(output_path)}


def export_jsonld(corpus: Path, output_path: Path) -> dict[str, int]:
    """Export work records to Schema.org ScholarlyArticle JSON-LD format."""
    graph: list[dict[str, Any]] = []
    for record_dir in sorted((corpus / "records").glob("work_*")):
        work = read_json(record_dir / "work.json", {})
        if not work:
            continue

        item: dict[str, Any] = {
            "@type": "ScholarlyArticle",
            "@id": f"urn:paperweave:work:{work['work_id']}",
            "name": work.get("title"),
        }
        if work.get("authors"):
            item["author"] = [{"@type": "Person", "name": a} for a in work["authors"]]
        if work.get("year"):
            item["datePublished"] = str(work["year"])
        if work.get("doi"):
            item["identifier"] = f"https://doi.org/{work['doi']}"

        graph.append(item)

    container = {
        "@context": "https://schema.org",
        "@graph": graph,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(container, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("Exported %d items to JSON-LD at %s", len(graph), output_path)
    return {"exported": len(graph), "format": "jsonld", "output": str(output_path)}
