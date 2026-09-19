"""Synthesis reports and cross-document literature review generation."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .hashing import sha256_file
from .io import read_json, write_json
from .manifest import load_manifest, now, save_manifest, update_stage
from .quality_report import write_quality_report
from .semantic import canonicalize_dataset_name

logger = logging.getLogger(__name__)


def evidence_suffix(item: dict[str, Any]) -> str:
    """Format evidence locators into inline Markdown code citations."""
    refs = item.get("evidence", [])
    if not refs:
        return ""
    rendered = []
    for ref in refs:
        page = "?" if ref.get("page_index") is None else ref["page_index"] + 1
        rendered.append(f"`{ref['document_id']}:{ref['block_id']}:p{page}`")
    return " " + " ".join(rendered)


def render_statements(items: list[dict[str, Any]], empty: str = "Not extracted.") -> list[str]:
    """Render statement dictionaries into bulleted Markdown lines with citations."""
    if not items:
        return [empty]
    return [
        f"- {item['statement']}{evidence_suffix(item)}"
        + (
            " *(model-extracted; semantic support not verified)*"
            if item.get("support_status") == "evidence_cited_unverified"
            else ""
        )
        for item in items
    ]


def corpus_records(corpus: Path) -> Iterator[tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]]:
    """Yield tuples of (work, analysis, experiments, taxonomy) for each work in the corpus."""
    for record_dir in sorted((corpus / "records").glob("work_*")):
        work = read_json(record_dir / "work.json", {})
        analysis = read_json(record_dir / "analysis.json", {})
        experiments = read_json(record_dir / "experiments.json", {})
        taxonomy = read_json(record_dir / "taxonomy.json", {})
        if work:
            yield work, analysis, experiments, taxonomy


def write_methodology(corpus: Path, records: list[tuple[Any, ...]]) -> None:
    """Generate methodology.md report."""
    lines = ["# Corpus Methodology Analysis", "", "Evidence references use `document:block:page`.", ""]
    for work, analysis, _, taxonomy in records:
        lines.extend([f"## {work['title']}", "", "### Research problem", ""])
        lines.extend(render_statements(analysis.get("research_problem", [])))
        lines.extend(["", "### Methodology", ""])
        lines.extend(render_statements(analysis.get("methodology", [])))
        methods = taxonomy.get("facets", {}).get("method_family", [])
        if methods:
            lines.extend(["", "### Method families", ""])
            lines.extend(f"- {item['name']}" for item in methods)
        lines.append("")
    (corpus / "synthesis" / "methodology.md").write_text("\n".join(lines), encoding="utf-8")


def write_experiments(corpus: Path, records: list[tuple[Any, ...]]) -> None:
    """Generate experiments.md report."""
    lines = ["# Corpus Experiment and Result Analysis", ""]
    for work, _, experiments, _ in records:
        lines.extend([f"## {work['title']}", "", "### Datasets", ""])
        datasets = experiments.get("datasets", [])
        lines.extend(
            [f"- {canonicalize_dataset_name(item['name'])}{evidence_suffix(item)}" for item in datasets]
            or ["Not extracted."]
        )
        lines.extend(["", "### Metrics", ""])
        metrics = experiments.get("metrics", [])
        lines.extend([f"- {item['name']}{evidence_suffix(item)}" for item in metrics] or ["Not extracted."])
        lines.extend(["", "### Experimental details", ""])
        lines.extend(render_statements(experiments.get("implementation_details", [])))
        lines.extend(["", "### Reported numerical results", ""])
        lines.extend(render_statements(experiments.get("results", [])))
        lines.append("")
    (corpus / "synthesis" / "experiments.md").write_text("\n".join(lines), encoding="utf-8")


def write_datasets(corpus: Path, records: list[tuple[Any, ...]]) -> None:
    """Generate datasets.md cross-paper usage index."""
    # Collect usage, normalizing dataset names for deduplication
    raw_usage: dict[str, list[tuple[Any, Any]]] = {}
    display_names: dict[str, str] = {}  # canonical casefold key → best display name
    for work, _, experiments, taxonomy in records:
        for dataset in experiments.get("datasets", []):
            raw_name = dataset.get("name", "").strip()
            if not raw_name:
                continue
            name = canonicalize_dataset_name(raw_name)
            key = name.casefold()
            raw_usage.setdefault(key, []).append((work, dataset))
            if key not in display_names:
                display_names[key] = name
        for dataset in taxonomy.get("facets", {}).get("dataset", []):
            raw_name = dataset.get("name", "").strip()
            if not raw_name:
                continue
            name = canonicalize_dataset_name(raw_name)
            key = name.casefold()
            raw_usage.setdefault(key, []).append((work, dataset))
            if key not in display_names:
                display_names[key] = name

    lines = ["# Corpus Dataset Index", ""]
    if not raw_usage:
        lines.append("No datasets were deterministically identified.")
    for key in sorted(raw_usage):
        uses = raw_usage[key]
        name = display_names.get(key, key)
        lines.extend([f"## {name}", ""])
        # Deduplicate by work_id — don't repeat the same work for the same dataset
        seen_works: set[str] = set()
        for work, dataset in uses:
            wid = work.get("work_id", "")
            if wid in seen_works:
                continue
            seen_works.add(wid)
            lines.append(f"- **{work['title']}**{evidence_suffix(dataset)}")
        lines.append("")
    (corpus / "synthesis" / "datasets.md").write_text("\n".join(lines), encoding="utf-8")


def write_review(corpus: Path, records: list[tuple[Any, ...]]) -> None:
    """Generate literature_review.md faceted review index."""
    facets: dict[tuple[str, str], list[str]] = {}
    for work, _, _, taxonomy in records:
        for facet, assignments in taxonomy.get("facets", {}).items():
            for assignment in assignments:
                facets.setdefault((facet, assignment["name"]), []).append(work["title"])
    lines = [
        "# Evidence-Backed Literature Review Index",
        "",
        "This is a deterministic thematic index, not a model-authored narrative. Claims should be checked through the cited methodology and experiment reports.",
        "",
        "## Corpus scope",
        "",
        f"The corpus contains {len(records)} normalized scholarly works.",
        "",
    ]
    for (facet, label), titles in sorted(facets.items()):
        lines.extend([f"## {facet.replace('_', ' ').title()}: {label}", ""])
        lines.extend(f"- {title}" for title in sorted(titles))
        lines.append("")
    lines.extend(
        [
            "## Research gaps",
            "",
            "Gap claims are intentionally not generated by the deterministic pipeline. They require cross-paper interpretation and manual evidence review or a configured semantic model.",
            "",
        ]
    )
    (corpus / "synthesis" / "literature_review.md").write_text("\n".join(lines), encoding="utf-8")


def write_references(corpus: Path, records: list[tuple[Any, ...]]) -> None:
    """Generate references.md bibliographic citations report."""
    lines = [
        "# Corpus Extracted Bibliographic References",
        "",
        "References extracted across normalized works with in-corpus provenance.",
        "",
    ]
    total_refs = 0
    for work, _, _, _ in records:
        work_id = work["work_id"]
        ref_file = corpus / "records" / work_id / "references.json"
        ref_data = read_json(ref_file, {})
        refs = ref_data.get("references", [])
        total_refs += len(refs)
        lines.extend([f"## {work['title']}", f"*Work ID: `{work_id}` — {len(refs)} citations extracted*", ""])
        if not refs:
            lines.extend(["No bibliography section was deterministically extracted.", ""])
            continue
        for ref in refs:
            raw = ref.get("raw", "").strip()
            ev = ref.get("evidence")
            suffix = f" `{ev['document_id']}:{ev['block_id']}`" if ev else ""
            lines.append(f"- {raw}{suffix}")
        lines.append("")
    (corpus / "synthesis" / "references.md").write_text("\n".join(lines), encoding="utf-8")


def write_all_papers(corpus: Path, records: list[tuple[Any, ...]]) -> None:
    """Generate all_papers.md unified document text."""
    lines = ["# Complete Normalized Corpus", ""]
    for work, _, _, _ in records:
        for document_id in work["document_ids"]:
            paper_path = corpus / "papers" / document_id / "paper.md"
            lines.extend(["---", "", f"# {work['title']}", "", f"Document ID: `{document_id}`", ""])
            if paper_path.exists():
                markdown = paper_path.read_text(encoding="utf-8", errors="ignore")
                asset_prefix = f"../papers/{document_id}/assets/"
                markdown = markdown.replace("](assets/", f"]({asset_prefix}")
                markdown = markdown.replace('src="assets/', f'src="{asset_prefix}')
                lines.append(markdown)
            lines.append("")
    (corpus / "synthesis" / "all_papers.md").write_text("\n".join(lines), encoding="utf-8")


def synthesis_fingerprints(corpus: Path) -> dict[str, str]:
    """Hash every structured and full-text input that contributes to synthesis reports."""
    fingerprints = {}
    for record_dir in sorted((corpus / "records").glob("work_*")):
        work = read_json(record_dir / "work.json", {})
        if not work:
            continue
        parts = []
        for name in ("work.json", "analysis.json", "experiments.json", "taxonomy.json", "references.json"):
            path = record_dir / name
            if path.is_file():
                parts.append(f"{name}:{sha256_file(path)}")
        for document_id in work.get("document_ids", []):
            paper = corpus / "papers" / document_id / "paper.md"
            if paper.is_file():
                parts.append(f"{document_id}:{sha256_file(paper)}")
        fingerprints[work["work_id"]] = hashlib.sha256("\n".join(parts).encode()).hexdigest()
    return fingerprints


def synthesize_incremental(corpus: Path, changed_work_ids: set[str] | None = None) -> dict[str, int]:
    """Skip synthesis only when all contributing content fingerprints are unchanged."""
    state_file = corpus / "manifests" / "synthesis_state.json"
    state = read_json(state_file, {})
    current = synthesis_fingerprints(corpus)
    previous = state.get("fingerprints", {})
    detected_changes = {work_id for work_id, digest in current.items() if previous.get(work_id) != digest}
    detected_changes.update(set(previous) - set(current))
    detected_changes.update(changed_work_ids or set())
    expected_reports = {
        "methodology.md",
        "experiments.md",
        "datasets.md",
        "literature_review.md",
        "references.md",
        "all_papers.md",
    }
    reports_exist = (
        all((corpus / "synthesis" / name).is_file() for name in expected_reports) and (corpus / "README.md").is_file()
    )
    if state_file.is_file() and reports_exist and not detected_changes and previous == current:
        logger.info("Synthesis is up-to-date. Skipping full regeneration.")
        return {"works": len(current), "reports": 6, "changed_works": 0, "regenerated": 0}

    result = synthesize_corpus(corpus)
    result.update({"changed_works": len(detected_changes), "regenerated": 1})
    return result


def synthesize_corpus(corpus: Path) -> dict[str, int]:
    """Generate all 6 grounded synthesis reports."""
    output_dir = corpus / "synthesis"
    output_dir.mkdir(parents=True, exist_ok=True)
    records = list(corpus_records(corpus))

    write_methodology(corpus, records)
    write_experiments(corpus, records)
    write_datasets(corpus, records)
    write_review(corpus, records)
    write_references(corpus, records)
    write_all_papers(corpus, records)
    write_quality_report(corpus, records)
    write_corpus_readme(corpus, records)

    manifest = load_manifest(corpus)
    included = {document_id for work, _, _, _ in records for document_id in work["document_ids"]}
    for record in manifest:
        if record["document_id"] in included:
            update_stage(record, "synthesis", "included")

    if manifest:
        save_manifest(corpus, manifest)

    write_json(
        corpus / "manifests" / "synthesis_state.json",
        {"fingerprints": synthesis_fingerprints(corpus), "updated_at": now()},
    )

    logger.info("Synthesized %d reports across %d scholarly works", 6, len(records))
    return {"works": len(records), "reports": 6}


def write_corpus_readme(corpus: Path, records: list[tuple[Any, ...]]) -> None:
    """Write a navigation page at the corpus root with summary statistics."""
    total_docs = sum(len(work.get("document_ids", [])) for work, _, _, _ in records)
    datasets: set[str] = set()
    metrics: set[str] = set()
    for _, _, experiments, taxonomy in records:
        for ds in experiments.get("datasets", []):
            raw = ds.get("name", "").strip()
            if raw:
                datasets.add(canonicalize_dataset_name(raw).casefold())
        for ds in taxonomy.get("facets", {}).get("dataset", []):
            raw = ds.get("name", "").strip()
            if raw:
                datasets.add(canonicalize_dataset_name(raw).casefold())
        for m in experiments.get("metrics", []):
            if m.get("name"):
                metrics.add(m["name"].strip())

    lines = [
        "# PaperWeave Corpus",
        "",
        f"This corpus indexes **{len(records)} scholarly works** across **{total_docs} document representations**.",
        "",
        "## Corpus Statistics",
        "",
        f"- **Unique Works:** {len(records)}",
        f"- **Document Representations:** {total_docs}",
        f"- **Identified Datasets:** {len(datasets)}",
        f"- **Extracted Metrics:** {len(metrics)}",
        "",
        "## Navigation & Synthesis Reports",
        "",
        "- [Datasets Index](synthesis/datasets.md) — Cross-paper dataset usage and benchmarking benchmarks",
        "- [Methodology](synthesis/methodology.md) — Core problem statements, contributions, and component breakdowns",
        "- [Experiments & Results](synthesis/experiments.md) — Quantitative metrics, results, and ablation studies",
        "- [Literature Review](synthesis/literature_review.md) — Categorized state-of-the-art review and open challenges",
        "- [References & Bibliography](synthesis/references.md) — Deterministically extracted bibliographic citations",
        "- [Combined Paper Text](synthesis/all_papers.md) — Unified full text of all papers with preserved assets",
        "- [Citation Graph](synthesis/citation_graph.md) — Cross-document citation and relationship graph",
        "- [Quality Audit Report](synthesis/quality_report.md) — Automated audit of grouping, dataset hygiene, and evidence provenance",
        "",
        "`papers/` contains normalized individual documents. `collections/` contains generated topic views.",
        "The remaining directories store indexes, provenance, and reproducible machine-readable records.",
        "",
    ]
    (corpus / "README.md").write_text("\n".join(lines), encoding="utf-8")
