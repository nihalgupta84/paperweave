"""Deterministic and LLM-assisted semantic analysis and evidence extraction."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .io import read_json, read_jsonl, write_json
from .manifest import load_manifest, save_manifest, update_stage
from .references import extract_and_save_references
from .validation import validate_analysis, validate_experiments, validate_work

logger = logging.getLogger(__name__)

DEFAULT_ENTITIES_FILE = Path(__file__).resolve().parent / "taxonomies" / "entities.json"


def load_entities(custom_path: str | Path | None = None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Load target datasets and metrics tuples from a JSON configuration."""
    target = Path(custom_path).expanduser().resolve() if custom_path else DEFAULT_ENTITIES_FILE
    data = read_json(target, {})
    datasets = tuple(data.get("datasets", []))
    metrics = tuple(data.get("metrics", []))
    if not datasets or not metrics:
        # Fallback to defaults if file missing or corrupt
        datasets = (
            "ImageNet",
            "COCO",
            "CIFAR-10",
            "CIFAR-100",
            "MNIST",
            "Cityscapes",
            "Twitter",
            "Reddit",
            "eRisk",
            "CLPsych",
            "DAIC-WOZ",
            "Sintel",
            "KITTI",
        )
        metrics = (
            "accuracy",
            "precision",
            "recall",
            "F1",
            "F1-score",
            "AUC",
            "AUROC",
            "mAP",
            "IoU",
            "Dice",
            "EPE",
            "endpoint error",
            "Fl-all",
            "FPS",
            "latency",
            "parameters",
            "FLOPs",
        )
    return datasets, metrics


def evidence(block: dict[str, Any]) -> dict[str, Any]:
    """Generate an evidence locator dict for a given block."""
    return {
        "document_id": block["document_id"],
        "block_id": block["block_id"],
        "page_index": block.get("page_index"),
        "section": " > ".join(block.get("section_path") or []),
    }


def statement(block: dict[str, Any], text: str | None = None) -> dict[str, Any]:
    """Generate a supported statement citing the provided block."""
    return {
        "statement": text or block.get("text", "").strip(),
        "support_status": "supported",
        "evidence": [evidence(block)],
    }


def substantive(block: dict[str, Any]) -> bool:
    """Check if a block contains substantive text."""
    text = block.get("text", "").strip()
    return block.get("type") not in {"header", "footer", "page_footnote"} and len(text) >= 80


def select(blocks: list[dict[str, Any]], roles: set[str], limit: int) -> list[dict[str, Any]]:
    """Select substantive blocks matching specific section roles."""
    selected = [block for block in blocks if block.get("section_role") in roles and substantive(block)]
    return selected[:limit]


def find_mentions(blocks: list[dict[str, Any]], terms: tuple[str, ...]) -> list[dict[str, Any]]:
    """Find entity mentions with source block citations."""
    found = {}
    for block in blocks:
        lowered = block.get("text", "").lower()
        for term in terms:
            if term.lower() in lowered and term.lower() not in found:
                found[term.lower()] = {"name": term, "evidence": [evidence(block)]}
    return list(found.values())


def result_sentences(blocks: list[dict[str, Any]], metrics: tuple[str, ...], limit: int = 20) -> list[dict[str, Any]]:
    """Extract candidate result sentences containing numerical digits and metric keywords."""
    results = []
    metric_pattern = "|".join(re.escape(metric) for metric in metrics)
    for block in blocks:
        if block.get("section_role") not in {"results", "experiments", "datasets"}:
            continue
        for sentence_text in re.split(r"(?<=[.!?])\s+", block.get("text", "")):
            if re.search(r"\d", sentence_text) and re.search(metric_pattern, sentence_text, re.I):
                results.append(statement(block, sentence_text.strip()))
                if len(results) >= limit:
                    return results
    return results


def analyze_document(
    paper_dir: Path,
    corpus: Path,
    datasets: tuple[str, ...] | None = None,
    metrics: tuple[str, ...] | None = None,
) -> bool:
    """Perform deterministic analysis and evidence extraction on a single normalized document."""
    document = read_json(paper_dir / "document.json", {})
    blocks = read_jsonl(paper_dir / "sections.jsonl") or read_jsonl(paper_dir / "blocks.jsonl")
    if not document or not blocks:
        return False

    if datasets is None or metrics is None:
        default_ds, default_met = load_entities()
        datasets = datasets or default_ds
        metrics = metrics or default_met

    work_id = document["work_id"]
    record_dir = corpus / "records" / work_id
    problem_blocks = select(blocks, {"abstract", "introduction"}, 2)
    method_blocks = select(blocks, {"methodology"}, 6)
    if not method_blocks:
        method_blocks = select(blocks, {"abstract"}, 2)
    experiment_blocks = select(blocks, {"experiments", "datasets"}, 6)
    limitation_blocks = select(blocks, {"limitations", "discussion", "conclusion"}, 3)
    found_datasets = find_mentions(blocks, datasets)
    found_metrics = find_mentions(blocks, metrics)

    # Extract bibliographic references
    extract_and_save_references(paper_dir, record_dir, document["document_id"])

    existing_work = read_json(record_dir / "work.json", {})
    document_ids = list(existing_work.get("document_ids", []))
    if document["document_id"] not in document_ids:
        document_ids.append(document["document_id"])

    work = {
        "schema_version": "1.0",
        "work_id": work_id,
        "title": document.get("title", paper_dir.name),
        "authors": document.get("authors") or existing_work.get("authors", []),
        "year": document.get("year") or existing_work.get("year"),
        "doi": document.get("doi") or existing_work.get("doi"),
        "arxiv_id": document.get("arxiv_id") or existing_work.get("arxiv_id"),
        "document_ids": sorted(document_ids),
        "merge_status": "title_matched" if len(document_ids) > 1 else "unreviewed",
    }

    analysis = {
        "schema_version": "1.0",
        "work_id": work_id,
        "document_id": document["document_id"],
        "extraction_mode": "deterministic_extractive",
        "research_problem": [statement(block) for block in problem_blocks],
        "methodology": [statement(block) for block in method_blocks],
        "contributions": [],
        "method_components": [],
        "training_objectives": [],
        "limitations": [statement(block) for block in limitation_blocks],
        "claims": [statement(block) for block in select(blocks, {"abstract", "conclusion"}, 5)],
    }

    experiments = {
        "schema_version": "1.0",
        "work_id": work_id,
        "document_id": document["document_id"],
        "datasets": found_datasets,
        "metrics": found_metrics,
        "baselines": [],
        "implementation_details": [statement(block) for block in experiment_blocks],
        "results": result_sentences(blocks, metrics),
        "ablations": [
            statement(block) for block in select(blocks, {"results"}, 4) if "ablation" in block.get("text", "").lower()
        ],
    }

    validate_work(work)
    validate_analysis(analysis)
    validate_experiments(experiments)

    document_record_dir = record_dir / "documents" / document["document_id"]
    write_json(record_dir / "work.json", work)
    write_json(document_record_dir / "analysis.json", analysis)
    write_json(document_record_dir / "experiments.json", experiments)
    rebuild_work_aggregates(record_dir, work)
    return True


def rebuild_work_aggregates(record_dir: Path, work: dict[str, Any]) -> None:
    """Recompute work-level aggregated analysis and experiment records from document records."""
    analyses = [read_json(path, {}) for path in sorted((record_dir / "documents").glob("doc_*/analysis.json"))]
    experiments = [read_json(path, {}) for path in sorted((record_dir / "documents").glob("doc_*/experiments.json"))]
    analysis_fields = (
        "research_problem",
        "methodology",
        "contributions",
        "method_components",
        "training_objectives",
        "limitations",
        "claims",
    )
    aggregate_analysis = {
        "schema_version": "1.0",
        "work_id": work["work_id"],
        "document_id": work["document_ids"][0],
        "document_ids": work["document_ids"],
        "extraction_mode": "deterministic_extractive_aggregate",
    }
    for field in analysis_fields:
        aggregate_analysis[field] = [item for value in analyses for item in value.get(field, [])]

    experiment_fields = (
        "datasets",
        "metrics",
        "baselines",
        "implementation_details",
        "results",
        "ablations",
    )
    aggregate_experiments = {
        "schema_version": "1.0",
        "work_id": work["work_id"],
        "document_id": work["document_ids"][0],
        "document_ids": work["document_ids"],
    }
    for field in experiment_fields:
        aggregate_experiments[field] = [item for value in experiments for item in value.get(field, [])]

    # Aggregate references
    all_refs = []
    seen_refs = set()
    for ref_path in sorted((record_dir / "documents").glob("doc_*/references.json")):
        ref_data = read_json(ref_path, {})
        for ref_item in ref_data.get("references", []):
            raw = ref_item.get("raw", "").strip()
            if raw and raw not in seen_refs:
                seen_refs.add(raw)
                all_refs.append(ref_item)
    write_json(record_dir / "references.json", {"work_id": work["work_id"], "references": all_refs})

    validate_analysis(aggregate_analysis)
    validate_experiments(aggregate_experiments)
    write_json(record_dir / "analysis.json", aggregate_analysis)
    write_json(record_dir / "experiments.json", aggregate_experiments)


def analyze_corpus(corpus: Path, force: bool = False, entities_path: str | Path | None = None) -> dict[str, int]:
    """Analyze all normalized documents in the corpus."""
    count = skipped = 0
    manifest = load_manifest(corpus)
    records_by_id = {record["document_id"]: record for record in manifest}
    datasets, metrics = load_entities(entities_path)

    for paper_dir in sorted((corpus / "papers").glob("doc_*")):
        document = read_json(paper_dir / "document.json", {})
        if not document:
            continue
        output = corpus / "records" / document["work_id"] / "documents" / document["document_id"] / "analysis.json"
        if output.exists() and not force:
            skipped += 1
            continue
        completed = analyze_document(paper_dir, corpus, datasets=datasets, metrics=metrics)
        count += int(completed)
        if completed and document["document_id"] in records_by_id:
            update_stage(records_by_id[document["document_id"]], "analysis", "complete", mode="deterministic")

    if manifest:
        save_manifest(corpus, manifest)
    logger.info("Corpus analysis finished: %d analyzed, %d skipped", count, skipped)
    return {"documents": count, "skipped": skipped}


ENRICHMENT_FIELDS = (
    "contributions",
    "method_components",
    "training_objectives",
    "limitations",
    "datasets",
    "metrics",
    "results",
)


def enrichment_schema() -> dict[str, Any]:
    """Schema for model-assisted structured fact extraction."""
    item = {
        "type": "object",
        "required": ["statement", "evidence_block_ids"],
        "properties": {
            "statement": {"type": "string"},
            "evidence_block_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        },
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "required": list(ENRICHMENT_FIELDS),
        "properties": {field: {"type": "array", "items": item} for field in ENRICHMENT_FIELDS},
        "additionalProperties": False,
    }


def enrich_document(paper_dir: Path, corpus: Path, provider: Any) -> tuple[bool, str | None]:
    """Enrich document analysis using a local or remote model provider with strict provenance checks."""
    document = read_json(paper_dir / "document.json", {})
    blocks = [block for block in read_jsonl(paper_dir / "sections.jsonl") if substantive(block)]
    if not document or not blocks:
        return False, "No normalized document blocks"

    selected = [
        block
        for block in blocks
        if block.get("section_role")
        in {"abstract", "methodology", "datasets", "experiments", "results", "limitations", "conclusion"}
    ][:80]
    selected = selected or blocks[:40]
    source = "\n\n".join(
        f"BLOCK_ID={block['block_id']} SECTION={block.get('section_role')}\n{block['text'][:1800]}"
        for block in selected
    )[:60000]

    prompt = (
        "Extract only facts explicitly supported by the supplied paper blocks. "
        "Every item must cite one or more exact BLOCK_ID values. Do not infer missing facts. "
        "For datasets and metrics, put the entity name in statement. Return JSON matching the schema.\n\n" + source
    )

    try:
        generated = provider.generate_json(prompt, enrichment_schema())
    except Exception as error:
        return False, str(error)

    by_id = {block["block_id"]: block for block in blocks}

    def block_cited(items: Any) -> list[dict[str, Any]]:
        output = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            ids = item.get("evidence_block_ids", [])
            if not item.get("statement") or not ids or any(block_id not in by_id for block_id in ids):
                continue
            output.append(
                {
                    "statement": item["statement"].strip(),
                    "support_status": "evidence_cited_unverified",
                    "evidence": [evidence(by_id[block_id]) for block_id in ids],
                }
            )
        return output

    record_dir = corpus / "records" / document["work_id"]
    document_dir = record_dir / "documents" / document["document_id"]
    analysis = read_json(document_dir / "analysis.json", {})
    experiments = read_json(document_dir / "experiments.json", {})

    for field in ("contributions", "method_components", "training_objectives", "limitations"):
        values = block_cited(generated.get(field, []))
        if values:
            analysis[field] = values

    for field in ("datasets", "metrics"):
        values = block_cited(generated.get(field, []))
        if values:
            experiments[field] = [
                {
                    "name": item["statement"],
                    "evidence": item["evidence"],
                    "support_status": "evidence_cited_unverified",
                }
                for item in values
            ]

    values = block_cited(generated.get("results", []))
    if values:
        experiments["results"] = values

    analysis["extraction_mode"] = "llm_enriched_evidence_validated"
    validate_analysis(analysis)
    validate_experiments(experiments)
    write_json(document_dir / "analysis.json", analysis)
    write_json(document_dir / "experiments.json", experiments)
    work = read_json(record_dir / "work.json", {})
    rebuild_work_aggregates(record_dir, work)
    return True, None


def enrich_corpus(corpus: Path, resolution: Any, force: bool = False) -> dict[str, Any]:
    """Optionally enrich all analyzed documents with model generation."""
    if resolution.effective == "deterministic":
        return {
            "requested": resolution.requested,
            "effective": "deterministic",
            "enriched": 0,
            "fallback_reason": resolution.fallback_reason,
        }

    enriched = failed = 0
    errors = []
    manifest = load_manifest(corpus)
    records_by_id = {record["document_id"]: record for record in manifest}

    for paper_dir in sorted((corpus / "papers").glob("doc_*")):
        document = read_json(paper_dir / "document.json", {})
        if not document:
            continue
        record = records_by_id.get(document["document_id"])
        if record and record.get("stages", {}).get("analysis", {}).get("mode") == resolution.effective and not force:
            continue
        ok, error = enrich_document(paper_dir, corpus, resolution.provider)
        if ok:
            enriched += 1
            if record:
                update_stage(record, "analysis", "complete", mode=resolution.effective)
        else:
            failed += 1
            errors.append({"document_id": document["document_id"], "error": error})
            if record:
                update_stage(record, "analysis", "complete", mode="deterministic", fallback_reason=error)

    if manifest:
        save_manifest(corpus, manifest)
    return {
        "requested": resolution.requested,
        "effective": resolution.effective if enriched else "deterministic",
        "enriched": enriched,
        "failed_with_deterministic_fallback": failed,
        "errors": errors,
    }


def validate_evidence(corpus: Path) -> dict[str, int]:
    """Verify document, block, page, and section coordinates for every evidence locator."""
    valid = invalid = 0
    block_index: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for paper_dir in (corpus / "papers").glob("doc_*"):
        for block in read_jsonl(paper_dir / "sections.jsonl"):
            block_index[block["document_id"]][block["block_id"]] = block

    for path in (corpus / "records").glob("work_*/*.json"):
        value = read_json(path, {})
        stack = [value]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                if "block_id" in item and "document_id" in item:
                    block = block_index.get(item["document_id"], {}).get(item["block_id"])
                    expected_section = " > ".join(block.get("section_path") or []) if block else None
                    coordinates_match = bool(block)
                    if block and "page_index" in item:
                        coordinates_match = coordinates_match and item["page_index"] == block.get("page_index")
                    if block and "section" in item:
                        coordinates_match = coordinates_match and item["section"] == expected_section
                    if coordinates_match:
                        valid += 1
                    else:
                        invalid += 1
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)
    return {"valid": valid, "invalid": invalid}
