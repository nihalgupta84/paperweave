"""Corpus-level self-audit and quality report generation."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from .io import read_jsonl
from .semantic import DATASET_FALSE_POSITIVES, DATASET_STOPWORDS, validate_evidence

logger = logging.getLogger(__name__)


def generate_quality_report(corpus: Path, records: list[tuple[Any, ...]]) -> str:
    """Audit grouping, dataset extraction, metric coverage, and evidence integrity.

    Returns the Markdown content of the quality report.
    """
    total_works = len(records)
    total_docs = sum(len(work.get("document_ids", [])) for work, _, _, _ in records)

    # 1. Grouping Audit
    multi_doc_works = [work for work, _, _, _ in records if len(work.get("document_ids", [])) > 1]
    candidate_file = corpus / "manifests" / "work_match_candidates.jsonl"
    if not candidate_file.is_file():
        candidate_file = corpus / "manifests" / "work_candidates.jsonl"
    candidates = read_jsonl(candidate_file) if candidate_file.is_file() else []

    # Map document_id to work_id
    doc_to_work: dict[str, str] = {}
    for work, _, _, _ in records:
        for doc_id in work.get("document_ids", []):
            doc_to_work[doc_id] = work.get("work_id", "")

    unmerged_candidates = []
    for cand in candidates:
        left_doc = cand.get("left_document_id", "")
        right_doc = cand.get("right_document_id", "")
        left_work = doc_to_work.get(left_doc)
        right_work = doc_to_work.get(right_doc)
        if left_work and right_work and left_work != right_work:
            unmerged_candidates.append(cand)

    # 2. Dataset Audit
    all_datasets: dict[str, list[str]] = {}
    for work, _, experiments, taxonomy in records:
        work_title = work.get("title", "Untitled")
        for ds in experiments.get("datasets", []):
            name = ds.get("name", "").strip()
            if name:
                all_datasets.setdefault(name, []).append(work_title)
        for ds in taxonomy.get("facets", {}).get("dataset", []):
            name = ds.get("name", "").strip()
            if name:
                all_datasets.setdefault(name, []).append(work_title)

    suspicious_datasets = []
    for name, works in all_datasets.items():
        reasons = []
        name_lower = name.casefold()
        if name_lower in DATASET_STOPWORDS:
            reasons.append("matches stopword")
        if name_lower in DATASET_FALSE_POSITIVES:
            reasons.append("matches known false positive")
        if len(name) <= 2:
            reasons.append("suspiciously short (<= 2 chars)")
        if re.search(r"[.!?]\s+[A-Z]", name):
            reasons.append("contains sentence boundary")
        if reasons:
            suspicious_datasets.append({"name": name, "reasons": reasons, "works": works})

    # 3. Metric & Results Coverage Audit
    works_with_metrics = 0
    works_with_results = 0
    works_missing_metrics = []
    total_metrics_found = 0
    all_metric_names: set[str] = set()

    for work, _, experiments, _ in records:
        metrics = experiments.get("metrics", [])
        results = experiments.get("results", [])
        total_metrics_found += len(metrics)
        for m in metrics:
            all_metric_names.add(m.get("name", ""))
        has_m = bool(metrics)
        has_r = bool(results)
        if has_m:
            works_with_metrics += 1
        if has_r:
            works_with_results += 1
        if not has_m and not has_r:
            works_missing_metrics.append(work.get("title", "Untitled"))

    # 4. Evidence Integrity
    evidence_stats = validate_evidence(corpus)
    valid_ev = evidence_stats.get("valid", 0)
    invalid_ev = evidence_stats.get("invalid", 0)
    total_ev = valid_ev + invalid_ev
    ev_rate = (valid_ev / total_ev * 100) if total_ev > 0 else 100.0

    # 5. Extraction Mode Breakdown
    mode_counts: dict[str, int] = {}
    for _, analysis, _, _ in records:
        mode = analysis.get("extraction_mode", "unknown")
        mode_counts[mode] = mode_counts.get(mode, 0) + 1

    # 6. Build Report
    lines = [
        "# Corpus Quality Audit Report",
        "",
        "This report provides an automated audit of ingestion grouping, dataset hygiene,",
        "metric coverage, evidence provenance, and extraction modes across the corpus.",
        "",
        "## Executive Summary",
        "",
        "| Metric | Value | Status |",
        "|---|---|---|",
        f"| Total Scholarly Works | {total_works} | Info |",
        f"| Total Document Representations | {total_docs} | Info |",
        f"| Multi-Document Merged Works | {len(multi_doc_works)} | {'Notice' if multi_doc_works else 'Info'} |",
        f"| Unique Datasets Identified | {len(all_datasets)} | {'Warning' if suspicious_datasets else 'Pass'} |",
        f"| Suspicious Dataset Candidates | {len(suspicious_datasets)} | {'Pass' if not suspicious_datasets else 'Review Needed'} |",
        f"| Works with Extracted Metrics | {works_with_metrics}/{total_works} | {'Pass' if works_with_metrics > 0 or total_works == 0 else 'Notice'} |",
        f"| Evidence Locator Validity | {valid_ev}/{total_ev} ({ev_rate:.1f}%) | {'Pass' if invalid_ev == 0 else 'Review Needed'} |",
        "",
    ]

    # Grouping Section
    lines.extend([
        "## 1. Grouping & Document Deduplication Audit",
        "",
        f"- **Multi-document works ({len(multi_doc_works)}):**",
    ])
    if multi_doc_works:
        for w in multi_doc_works:
            lines.append(f"  - **{w.get('title', 'Untitled')}** (`{w.get('work_id')}`): {len(w.get('document_ids', []))} documents merged")
    else:
        lines.append("  - None (each work consists of a single document representation).")
    lines.append("")

    if unmerged_candidates:
        lines.extend([
            f"- **Unmerged Title Candidate Pairs ({len(unmerged_candidates)}):**",
            "  *The following pairs share title similarity but were kept as distinct works (e.g. distinct DOIs or insufficient author overlap):*",
        ])
        for c in unmerged_candidates[:15]:
            lines.append(
                f"  - `{c.get('left_document_id')}` vs `{c.get('right_document_id')}` "
                f"(similarity: {c.get('similarity', 0):.2f})"
            )
        if len(unmerged_candidates) > 15:
            lines.append(f"  - *...and {len(unmerged_candidates) - 15} more.*")
    else:
        lines.append("- **Candidate Pairs:** No unmerged high-similarity candidates detected.")
    lines.append("")

    # Dataset Section
    lines.extend([
        "## 2. Dataset Mention Hygiene Audit",
        "",
        f"Total unique datasets found across the corpus: **{len(all_datasets)}**.",
        "",
    ])
    if suspicious_datasets:
        lines.append("### Flagged Suspicious Mentions")
        lines.append("")
        for item in suspicious_datasets:
            lines.append(f"- **`{item['name']}`**: {', '.join(item['reasons'])} *(cited in: {', '.join(item['works'][:3])})*")
        lines.append("")
    else:
        lines.append("No suspicious dataset names detected. All candidates passed stopword, boundary, and entity validation.")
        lines.append("")

    # Metrics Section
    lines.extend([
        "## 3. Quantitative Metric & Result Coverage",
        "",
        f"- Works with extracted metrics: **{works_with_metrics}/{total_works}**",
        f"- Works with quantitative result statements: **{works_with_results}/{total_works}**",
        f"- Total metric entity mentions: **{total_metrics_found}** ({len(all_metric_names)} distinct metrics)",
    ])
    if all_metric_names:
        sample_metrics = sorted(all_metric_names)[:20]
        lines.append(f"- Identified metrics include: {', '.join(f'`{m}`' for m in sample_metrics)}")
    if works_missing_metrics:
        lines.append("")
        lines.append("### Works Without Quantitative Metrics or Results")
        for title in works_missing_metrics[:10]:
            lines.append(f"- {title}")
        if len(works_missing_metrics) > 10:
            lines.append(f"- *...and {len(works_missing_metrics) - 10} more.*")
    lines.append("")

    # Evidence Integrity Section
    lines.extend([
        "## 4. Evidence Integrity & Grounding Audit",
        "",
        f"- **Valid evidence locators:** {valid_ev}",
        f"- **Invalid evidence locators:** {invalid_ev}",
        f"- **Provenance resolution rate:** {ev_rate:.1f}%",
        "",
    ])
    if invalid_ev > 0:
        lines.append("> [!WARNING]")
        lines.append(f"> {invalid_ev} evidence locators could not be resolved to valid document blocks. Run `paperweave analyze --force` to re-ground.")
        lines.append("")

    # Extraction Modes Section
    lines.extend([
        "## 5. Extraction Mode Breakdown",
        "",
    ])
    for mode, count in sorted(mode_counts.items()):
        lines.append(f"- `{mode}`: {count} work(s)")
    lines.append("")

    return "\n".join(lines)


def write_quality_report(corpus: Path, records: list[tuple[Any, ...]]) -> Path:
    """Generate and save synthesis/quality_report.md."""
    content = generate_quality_report(corpus, records)
    report_path = corpus / "synthesis" / "quality_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(content, encoding="utf-8")
    return report_path
