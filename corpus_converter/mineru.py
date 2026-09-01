"""Normalize version-variable MinerU output into stable document directories."""

import argparse
import hashlib
import json
import shutil
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .hashing import sha256_file
from .io import read_json as load_json
from .io import read_jsonl as load_jsonl
from .io import write_jsonl
from .manifest import update_stage
from .quality import assess_document
from .validation import validate_block, validate_document

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file_optional(path: Path | None) -> str | None:
    """Wrapper that returns None for missing paths instead of raising."""
    if not path or not path.exists():
        return None
    return sha256_file(path)


def find_largest(directory: Path, patterns: list[str]) -> Path | None:
    files: list[Path] = []
    for pattern in patterns:
        files.extend(directory.glob(pattern))
    files = [path for path in files if path.is_file()]
    return max(files, key=lambda path: path.stat().st_size) if files else None


def find_auto_dir(paper_root: Path) -> Path | None:
    direct = paper_root / "auto"
    if direct.is_dir():
        return direct
    candidates = [path for path in paper_root.rglob("auto") if path.is_dir()]
    return min(candidates, key=lambda path: len(path.parts)) if candidates else None


def flatten_content(value: Any, inherited_page: int | None = None) -> Iterable[dict[str, Any]]:
    """Yield blocks from MinerU flat v1 or page-oriented v2 content JSON."""
    if isinstance(value, list):
        for item in value:
            yield from flatten_content(item, inherited_page)
        return
    if not isinstance(value, dict):
        return
    local_page = as_int(value.get("page_idx", value.get("page", value.get("page_no"))))
    page = local_page if local_page is not None else inherited_page
    if {"type", "text", "bbox", "img_path", "image_path", "table_body"}.intersection(value):
        block = dict(value)
        if page is not None and not any(key in block for key in ("page_idx", "page", "page_no")):
            block["page_idx"] = page
        yield block
        return
    children_found = False
    for key in ("blocks", "content", "items", "body", "children", "pages"):
        if key in value:
            children_found = True
            yield from flatten_content(value[key], page)
    if not children_found:
        for child in value.values():
            if isinstance(child, list | dict):
                yield from flatten_content(child, page)


def content_text(value: Any) -> list[str]:
    parts = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "content" and isinstance(child, str) and child.strip():
                parts.append(child.strip())
            elif isinstance(child, dict | list):
                parts.extend(content_text(child))
    elif isinstance(value, list):
        for child in value:
            parts.extend(content_text(child))
    return parts


def as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def block_text(block: dict[str, Any]) -> str:
    parts = []
    for key in ("text", "table_body", "image_caption", "table_caption", "caption"):
        value = block.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
        elif isinstance(value, list):
            parts.extend(str(item).strip() for item in value if str(item).strip())
    if not parts and isinstance(block.get("content"), dict | list):
        parts.extend(content_text(block["content"]))
    return "\n".join(dict.fromkeys(parts))


def normalize_bbox(value: Any) -> list[float] | None:
    if not isinstance(value, list | tuple) or len(value) != 4:
        return None
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def source_image_path(block: dict[str, Any]) -> str | None:
    for key in ("img_path", "image_path", "path"):
        value = block.get(key)
        if isinstance(value, str) and Path(value).suffix.lower() in IMAGE_EXTENSIONS:
            return value
    return None


def stable_block_id(document_id: str, block: dict[str, Any], source_index: int) -> str:
    identity = {
        "document_id": document_id,
        "source_index": source_index,
        "type": block.get("type"),
        "page": block.get("page_idx", block.get("page", block.get("page_no"))),
        "bbox": block.get("bbox"),
        "text": block_text(block),
        "image": source_image_path(block),
    }
    encoded = json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()
    return f"blk_{hashlib.sha256(encoded).hexdigest()[:20]}"


def normalize_blocks(content_json: Path | None, document_id: str, parser_version: str | None):
    blocks = []
    data = load_json(content_json)
    if isinstance(data, list) and data and all(isinstance(page, list) for page in data):
        raw_blocks = (block for page_index, page in enumerate(data) for block in flatten_content(page, page_index))
    else:
        raw_blocks = flatten_content(data)
    for index, block in enumerate(raw_blocks):
        blocks.append(
            {
                "block_id": stable_block_id(document_id, block, index),
                "document_id": document_id,
                "type": str(block.get("type") or "unknown").lower(),
                "heading_level": as_int(
                    block.get(
                        "text_level",
                        block.get("content", {}).get("level") if isinstance(block.get("content"), dict) else None,
                    )
                ),
                "page_index": as_int(block.get("page_idx", block.get("page", block.get("page_no")))),
                "section_path": [],
                "text": block_text(block),
                "bbox": normalize_bbox(block.get("bbox")),
                "asset_path": source_image_path(block),
                "source": {
                    "parser": "mineru",
                    "parser_version": parser_version,
                    "source_file": content_json.name if content_json else None,
                    "source_index": index,
                },
            }
        )
    return blocks


def resolve_asset(auto_dir: Path, relative_path: str) -> Path | None:
    for candidate in (auto_dir / relative_path, auto_dir / "images" / Path(relative_path).name):
        if candidate.is_file():
            return candidate
    return None


def copy_assets(auto_dir: Path, paper_dir: Path, blocks: list[dict[str, Any]]) -> dict[str, str]:
    assets_dir = paper_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    requested = [block["asset_path"] for block in blocks if block.get("asset_path")]
    images_dir = auto_dir / "images"
    if images_dir.is_dir():
        requested.extend(str(path.relative_to(auto_dir)) for path in images_dir.iterdir() if path.is_file())
    mapping = {}
    for relative_path in dict.fromkeys(requested):
        source = resolve_asset(auto_dir, relative_path)
        if not source or source.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        short_hash = hashlib.sha256(source.read_bytes()).hexdigest()[:10]
        name = f"{source.stem}_{short_hash}{source.suffix.lower()}"
        destination = assets_dir / name
        if not destination.exists():
            shutil.copy2(source, destination)
        mapping[relative_path] = f"assets/{name}"
        mapping[Path(relative_path).name] = f"assets/{name}"
    for block in blocks:
        if block.get("asset_path") in mapping:
            block["asset_path"] = mapping[block["asset_path"]]
    return mapping


def rewrite_markdown_assets(text: str, mapping: dict[str, str]) -> str:
    for old, new in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
        text = text.replace(old, new)
    return text


def manifest_indexes(records):
    by_stem, by_hash = {}, {}
    for record in records:
        if record.get("selected_for_extraction") is False or record.get("format") not in {None, "pdf"}:
            continue
        file_name = record.get("file_name") or record.get("target_filename")
        if file_name:
            by_stem[Path(file_name).stem] = record
        if record.get("sha256"):
            by_hash[record["sha256"]] = record
    return by_stem, by_hash


def identify_document(paper_root, origin_pdf, by_stem, by_hash):
    digest = sha256_file_optional(origin_pdf)
    record = by_hash.get(digest) if digest else None
    record = record or by_stem.get(paper_root.name)
    if record:
        identity_hash = record.get("sha256") or digest or hashlib.sha256(paper_root.name.encode()).hexdigest()
        record.setdefault("document_id", f"doc_{identity_hash[:16]}")
        record.setdefault("work_id", f"work_{identity_hash[:16]}")
        record.setdefault("file_name", record.get("target_filename"))
        if not record.get("pdf_path") and record.get("target_path"):
            record["pdf_path"] = record["target_path"]
        return record
    fallback = digest or hashlib.sha256(paper_root.name.encode()).hexdigest()
    return {
        "document_id": f"doc_{fallback[:16]}",
        "work_id": f"work_{fallback[:16]}",
        "sha256": digest,
        "title": paper_root.name,
        "file_name": origin_pdf.name if origin_pdf else None,
        "pdf_path": None,
    }


def format_one(paper_root, papers_dir, by_stem, by_hash, parser_version, force):
    auto_dir = find_auto_dir(paper_root)
    if not auto_dir:
        print(f"NO_AUTO: {paper_root}")
        return "failed", None
    main_md = find_largest(auto_dir, ["*.md"])
    if not main_md:
        print(f"NO_MD: {paper_root}")
        return "failed", None
    v1_files = [path for path in auto_dir.glob("*content_list*.json") if "content_list_v2" not in path.name]
    content_json = max(v1_files, key=lambda path: path.stat().st_size) if v1_files else None
    content_json = content_json or find_largest(auto_dir, ["*content_list_v2*.json"])
    origin_pdf = find_largest(auto_dir, ["*_origin.pdf", "*.pdf"])
    record = identify_document(paper_root, origin_pdf, by_stem, by_hash)
    document_id = record["document_id"]
    paper_dir = papers_dir / document_id
    done_file = paper_dir / ".done"
    if done_file.exists() and not force:
        print(f"SKIP: {document_id} | {paper_root.name}")
        return "skipped", document_id

    paper_dir.mkdir(parents=True, exist_ok=True)
    blocks = normalize_blocks(content_json, document_id, parser_version)
    if not blocks:
        update_stage(record, "normalization", "failed", error="No MinerU content blocks found")
        print(f"NO_BLOCKS: {paper_root}")
        return "failed", document_id
    for block in blocks:
        validate_block(block)
    asset_map = copy_assets(auto_dir, paper_dir, blocks)
    markdown = rewrite_markdown_assets(main_md.read_text(encoding="utf-8", errors="ignore"), asset_map)
    (paper_dir / "paper.md").write_text(markdown, encoding="utf-8")
    write_jsonl(paper_dir / "blocks.jsonl", blocks)
    document = {
        "document_id": document_id,
        "work_id": record.get("work_id") or document_id.replace("doc_", "work_", 1),
        "sha256": record.get("sha256") or sha256_file_optional(origin_pdf),
        "format": "pdf",
        "version": "unknown",
        "title": record.get("title") or paper_root.name,
        "authors": record.get("authors", []),
        "year": record.get("year"),
        "doi": record.get("doi"),
        "arxiv_id": record.get("arxiv_id"),
        "source_path": record.get("canonical_path") or record.get("pdf_path"),
        "parser": {
            "name": "mineru",
            "version": parser_version,
            "processed_at": utc_now(),
            "raw_directory": str(auto_dir),
            "markdown_file": main_md.name,
            "content_file": content_json.name if content_json else None,
        },
        "block_count": len(blocks),
        "asset_count": len(set(asset_map.values())),
    }
    validate_document(document)
    (paper_dir / "document.json").write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    quality = assess_document(paper_dir)
    done_file.write_text("done\n", encoding="utf-8")
    update_stage(record, "extraction", "complete", parser="mineru")
    update_stage(record, "normalization", "complete", quality_status=quality["status"])
    print(f"DONE: {document_id} | blocks={len(blocks)} assets={document['asset_count']}")
    return "done", document_id


def format_mineru_output(
    corpus_dir: Path | None = None,
    mineru_raw: Path | None = None,
    out_dir: Path | None = None,
    parser_version: str | None = None,
    force: bool = False,
) -> dict[str, int]:
    """Normalize MinerU output into canonical PaperWeave document folders."""
    if corpus_dir:
        corpus_dir = corpus_dir.expanduser().resolve()
        raw_dir = corpus_dir / "raw" / "mineru"
        if not raw_dir.exists() and (corpus_dir / "mineru_raw").exists():
            raw_dir = corpus_dir / "mineru_raw"
        papers_dir = corpus_dir / "papers"
        canonical_manifest_path = corpus_dir / "manifests" / "documents.jsonl"
        manifest_path = canonical_manifest_path
        legacy = corpus_dir / "manifests" / "pdf_manifest.jsonl"
        if not manifest_path.exists() and legacy.exists():
            manifest_path = legacy
    elif mineru_raw and out_dir:
        raw_dir = mineru_raw.expanduser().resolve()
        papers_dir = out_dir.expanduser().resolve()
        manifest_path = raw_dir.parent / "manifests" / "documents.jsonl"
        canonical_manifest_path = manifest_path
    else:
        raise ValueError("use corpus_dir, or both mineru_raw and out_dir")

    if not raw_dir.exists():
        raise SystemExit(f"MinerU raw folder does not exist: {raw_dir}")
    papers_dir.mkdir(parents=True, exist_ok=True)
    records = load_jsonl(manifest_path)
    by_stem, by_hash = manifest_indexes(records)
    paper_roots = sorted(path for path in raw_dir.iterdir() if path.is_dir())
    counts = {"done": 0, "skipped": 0, "failed": 0}
    statuses = {}
    print(f"Found MinerU paper folders: {len(paper_roots)}")
    for index, paper_root in enumerate(paper_roots, 1):
        print(f"[{index}/{len(paper_roots)}] {paper_root.name}")
        status, document_id = format_one(paper_root, papers_dir, by_stem, by_hash, parser_version, force)
        counts[status] += 1
        if document_id:
            statuses[document_id] = "complete" if status in {"done", "skipped"} else "failed"

    records_by_id = {record.get("document_id"): record for record in records if record.get("document_id")}
    for record in records:
        if (
            record.get("selected_for_extraction")
            and record.get("format") == "pdf"
            and record.get("stages", {}).get("mineru", {}).get("status") == "failed"
        ):
            update_stage(record, "normalization", "skipped", reason="mineru_failed")
    for document_path in sorted(papers_dir.glob("doc_*/document.json")):
        document = load_json(document_path)
        if not isinstance(document, dict):
            continue
        document_id = document["document_id"]
        record = records_by_id.setdefault(document_id, {})
        record.update(
            {
                "document_id": document_id,
                "work_id": document["work_id"],
                "sha256": document.get("sha256"),
                "canonical_path": document.get("source_path") or document.get("source_pdf"),
                "file_name": Path(document.get("source_path") or document.get("source_pdf")).name
                if (document.get("source_path") or document.get("source_pdf"))
                else None,
                "title": document.get("title"),
                "status": "ready",
                "normalization_status": "complete",
                "updated_at": utc_now(),
            }
        )
    if records_by_id:
        write_jsonl(canonical_manifest_path, sorted(records_by_id.values(), key=lambda item: item["document_id"]))
    print("\nSummary")
    print(json.dumps(counts, indent=2))
    print(f"Output: {papers_dir}")
    return counts


def main() -> None:
    """Compatibility command-line entrypoint for MinerU normalization."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-dir", type=Path, help="Canonical corpus workspace.")
    parser.add_argument("--mineru-raw", type=Path, help="Legacy explicit MinerU output path.")
    parser.add_argument("--out-dir", type=Path, help="Legacy explicit normalized output path.")
    parser.add_argument("--parser-version")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    format_mineru_output(
        corpus_dir=args.corpus_dir,
        mineru_raw=args.mineru_raw,
        out_dir=args.out_dir,
        parser_version=args.parser_version,
        force=args.force,
    )


if __name__ == "__main__":
    main()
