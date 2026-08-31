import hashlib
from pathlib import Path

from .manifest import load_manifest, save_manifest, update_stage


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reconcile_mineru(corpus: Path) -> dict[str, int]:
    raw_dir = corpus / "raw" / "mineru"
    if not raw_dir.exists() and (corpus / "mineru_raw").exists():
        raw_dir = corpus / "mineru_raw"
    records = load_manifest(corpus)
    counts = {"complete": 0, "failed": 0, "skipped": 0}
    roots_by_stem = {path.name: path for path in raw_dir.iterdir() if path.is_dir()} if raw_dir.exists() else {}
    roots_by_hash = {}
    for origin in raw_dir.glob("*/auto/*_origin.pdf") if raw_dir.exists() else []:
        try:
            roots_by_hash[sha256_file(origin)] = origin.parents[1]
        except OSError:
            pass
    for record in records:
        if not record.get("selected_for_extraction") or record.get("format") != "pdf":
            counts["skipped"] += 1
            continue
        root = roots_by_stem.get(Path(record["canonical_path"]).stem) or roots_by_hash.get(record["sha256"])
        markdown = list((root / "auto").glob("*.md")) if root and (root / "auto").exists() else []
        if markdown:
            update_stage(record, "mineru", "complete", raw_directory=str(root))
            counts["complete"] += 1
        else:
            update_stage(record, "mineru", "failed", error="No MinerU Markdown output found")
            counts["failed"] += 1
    save_manifest(corpus, records)
    return counts
