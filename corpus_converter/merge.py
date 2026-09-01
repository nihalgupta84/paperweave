"""Safe work-record merging utilities for consolidating duplicate works."""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from .io import read_json, read_jsonl, write_json, write_jsonl
from .manifest import load_manifest, now, save_manifest
from .semantic import rebuild_work_aggregates
from .validation import validate_analysis, validate_document, validate_experiments, validate_taxonomy, validate_work

logger = logging.getLogger(__name__)


def _directory_digest(path: Path) -> str:
    """Return a stable digest for collision checking within document record directories."""
    digest = hashlib.sha256()
    for file_path in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(str(file_path.relative_to(path)).encode())
        digest.update(file_path.read_bytes())
    return digest.hexdigest()


def _normalized_identifier(value: Any, kind: str) -> str:
    """Normalize DOI and arXiv identifiers before identity comparison."""
    normalized = str(value or "").strip().casefold()
    prefixes = {
        "doi": ("https://doi.org/", "http://doi.org/", "doi:"),
        "arxiv": ("https://arxiv.org/abs/", "http://arxiv.org/abs/", "arxiv:"),
    }
    for prefix in prefixes[kind]:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
    return normalized.strip()


def strong_identity_match(left: dict[str, Any], right: dict[str, Any]) -> tuple[bool, str | None]:
    """Require an exact scholarly identifier before permitting automatic merging."""
    for field, kind in (("doi", "doi"), ("arxiv_id", "arxiv")):
        left_value = _normalized_identifier(left.get(field), kind)
        right_value = _normalized_identifier(right.get(field), kind)
        if left_value and left_value == right_value:
            return True, f"matching_{field}"
    return False, None


def merge_works(corpus: Path, primary_work_id: str, secondary_work_id: str, reason: str = "manual_merge") -> bool:
    """Merge two explicitly selected works while retaining recoverable snapshots of both originals."""
    if primary_work_id == secondary_work_id:
        logger.error("Cannot merge a work with itself: %s", primary_work_id)
        return False

    records_dir = corpus / "records"
    primary_dir = records_dir / primary_work_id
    secondary_dir = records_dir / secondary_work_id
    if not primary_dir.exists() or not secondary_dir.exists():
        logger.error("Cannot merge: one or both work directories do not exist.")
        return False

    primary_work = read_json(primary_dir / "work.json", {})
    secondary_work = read_json(secondary_dir / "work.json", {})
    if not primary_work or not secondary_work:
        logger.error("Cannot merge: one or both work records are missing or invalid.")
        return False

    primary_documents = primary_dir / "documents"
    secondary_documents = secondary_dir / "documents"
    if secondary_documents.exists():
        for source in secondary_documents.iterdir():
            target = primary_documents / source.name
            if source.is_dir() and target.exists() and _directory_digest(source) != _directory_digest(target):
                logger.error("Cannot merge: conflicting records exist for document %s", source.name)
                return False

    transaction_id = uuid4().hex[:12]
    staging_dir = records_dir / f".{primary_work_id}.merge-{transaction_id}"
    backup_dir = corpus / "quarantine" / "merged_works" / (f"{primary_work_id}__{secondary_work_id}__{transaction_id}")
    backup_dir.mkdir(parents=True, exist_ok=False)

    try:
        shutil.copytree(primary_dir, staging_dir)
        staging_documents = staging_dir / "documents"
        staging_documents.mkdir(parents=True, exist_ok=True)
        copied_doc_ids = []
        if secondary_documents.exists():
            for source in secondary_documents.iterdir():
                if not source.is_dir():
                    continue
                target = staging_documents / source.name
                if not target.exists():
                    shutil.copytree(source, target)
                copied_doc_ids.append(source.name)

        for document_dir in staging_documents.glob("doc_*"):
            for file_name, validator in (
                ("analysis.json", validate_analysis),
                ("experiments.json", validate_experiments),
            ):
                path = document_dir / file_name
                value = read_json(path, {})
                if value:
                    value["work_id"] = primary_work_id
                    validator(value)
                    write_json(path, value)

        merged_work = dict(primary_work)
        merged_work["document_ids"] = sorted(
            set(primary_work.get("document_ids", []) + secondary_work.get("document_ids", []))
        )
        merged_work["merge_status"] = f"merged_with_{secondary_work_id}"
        merged_work["merge_reason"] = reason
        for field in ("authors", "year", "doi", "arxiv_id"):
            if not merged_work.get(field) and secondary_work.get(field):
                merged_work[field] = secondary_work[field]

        validate_work(merged_work)
        write_json(staging_dir / "work.json", merged_work)
        rebuild_work_aggregates(staging_dir, merged_work)

        primary_taxonomy = read_json(primary_dir / "taxonomy.json", {})
        secondary_taxonomy = read_json(secondary_dir / "taxonomy.json", {})
        if primary_taxonomy or secondary_taxonomy:
            merged_taxonomy = dict(primary_taxonomy or secondary_taxonomy)
            merged_taxonomy["work_id"] = primary_work_id
            merged_facets = {}
            all_facets = set(primary_taxonomy.get("facets", {})) | set(secondary_taxonomy.get("facets", {}))
            for facet in all_facets:
                values = primary_taxonomy.get("facets", {}).get(facet, []) + secondary_taxonomy.get("facets", {}).get(
                    facet, []
                )
                unique = {value.get("id", value.get("name")): value for value in values}
                merged_facets[facet] = list(unique.values())
            merged_taxonomy["facets"] = merged_facets
            validate_taxonomy(merged_taxonomy)
            write_json(staging_dir / "taxonomy.json", merged_taxonomy)

        primary_backup = backup_dir / "primary_before"
        secondary_backup = backup_dir / "secondary_before"
        shutil.move(str(primary_dir), str(primary_backup))
        shutil.move(str(secondary_dir), str(secondary_backup))
        shutil.move(str(staging_dir), str(primary_dir))

        paper_document_backups = backup_dir / "paper_documents"
        for document_id in secondary_work.get("document_ids", []):
            document_path = corpus / "papers" / document_id / "document.json"
            document = read_json(document_path, {})
            if not document:
                continue
            paper_document_backups.mkdir(parents=True, exist_ok=True)
            shutil.copy2(document_path, paper_document_backups / f"{document_id}.json")
            document["work_id"] = primary_work_id
            validate_document(document)
            write_json(document_path, document)

        manifest = load_manifest(corpus)
        for record in manifest:
            if record.get("work_id") == secondary_work_id:
                record["work_id"] = primary_work_id
        save_manifest(corpus, manifest)

    except Exception as error:
        logger.exception("Merge transaction failed for %s and %s", primary_work_id, secondary_work_id)
        primary_backup = backup_dir / "primary_before"
        secondary_backup = backup_dir / "secondary_before"
        if primary_dir.exists() and primary_backup.exists():
            shutil.move(str(primary_dir), str(backup_dir / "failed_merged_output"))
        if primary_backup.exists() and not primary_dir.exists():
            shutil.move(str(primary_backup), str(primary_dir))
        if secondary_backup.exists() and not secondary_dir.exists():
            shutil.move(str(secondary_backup), str(secondary_dir))
        paper_document_backups = backup_dir / "paper_documents"
        if paper_document_backups.exists():
            for backup in paper_document_backups.glob("doc_*.json"):
                destination = corpus / "papers" / backup.stem / "document.json"
                if destination.parent.exists():
                    shutil.copy2(backup, destination)
        if staging_dir.exists():
            shutil.move(str(staging_dir), str(backup_dir / "failed_staging_output"))
        logger.error("Merge rolled back; diagnostic artifacts are under %s: %s", backup_dir, error)
        return False

    try:
        merge_log_file = corpus / "manifests" / "merge_log.jsonl"
        existing_logs = read_jsonl(merge_log_file)
        existing_logs.append(
            {
                "timestamp": now(),
                "primary_work_id": primary_work_id,
                "merged_work_id": secondary_work_id,
                "copied_documents": copied_doc_ids,
                "reason": reason,
                "backup_path": str(backup_dir.relative_to(corpus)),
            }
        )
        write_jsonl(merge_log_file, existing_logs)
    except OSError as error:
        logger.error("Merge committed but audit-log write failed: %s", error)

    logger.info("Merged %s into %s; originals retained at %s", secondary_work_id, primary_work_id, backup_dir)
    return True


def auto_merge_candidates(corpus: Path, threshold: float = 0.95) -> dict[str, Any]:
    """Merge candidates only when title confidence and a strong scholarly identifier both agree."""
    candidates_file = corpus / "manifests" / "work_match_candidates.jsonl"
    candidates = read_jsonl(candidates_file)
    manifest = {record["document_id"]: record for record in load_manifest(corpus)}

    merged_count = 0
    blocked_count = 0
    remaining_candidates = []
    for item in candidates:
        similarity = float(item.get("similarity", 0))
        left_doc = item.get("left_document_id")
        right_doc = item.get("right_document_id")
        if similarity < threshold or left_doc not in manifest or right_doc not in manifest:
            remaining_candidates.append(item)
            continue

        left_work_id = manifest[left_doc]["work_id"]
        right_work_id = manifest[right_doc]["work_id"]
        if left_work_id == right_work_id:
            continue
        left_work = read_json(corpus / "records" / left_work_id / "work.json", {})
        right_work = read_json(corpus / "records" / right_work_id / "work.json", {})
        identity_ok, identity_reason = strong_identity_match(left_work, right_work)
        if not identity_ok:
            item["status"] = "review_needed"
            item["auto_merge_blocked_reason"] = "no_matching_doi_or_arxiv_id"
            remaining_candidates.append(item)
            blocked_count += 1
            continue

        reason = f"auto:{identity_reason}:title_{similarity}"
        if merge_works(corpus, left_work_id, right_work_id, reason=reason):
            merged_count += 1
            manifest = {record["document_id"]: record for record in load_manifest(corpus)}
        else:
            remaining_candidates.append(item)

    write_jsonl(candidates_file, remaining_candidates)
    logger.info("Auto-merged %d candidates; blocked %d without strong identity", merged_count, blocked_count)
    return {
        "merged_count": merged_count,
        "blocked_without_strong_identity": blocked_count,
        "remaining_candidates": len(remaining_candidates),
    }


def merge_interactive(corpus: Path) -> dict[str, Any]:
    """Report candidate count and direct users to the explicit review workflow."""
    candidates = read_jsonl(corpus / "manifests" / "work_match_candidates.jsonl")
    return {
        "status": "review_needed",
        "candidate_pairs": len(candidates),
        "next_step": f"paperweave review --corpus {corpus} --interactive",
    }
