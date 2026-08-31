import hashlib
import re
import shutil
import zipfile
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from .io import write_jsonl
from .manifest import load_manifest, now, save_manifest, update_stage


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".html", ".htm"}
FORMAT_RANK = {"pdf": 0, "docx": 1, "html": 2}
BAD_TITLE_WORDS = {"microsoft word", "untitled", "download", "index"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean_title(value: str) -> str:
    value = re.sub(r"[\r\n\t]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" .,:;|-_")
    return value[:300]


def valid_title(value: str) -> bool:
    lowered = value.lower()
    return (
        8 <= len(value) <= 300
        and len(re.findall(r"[A-Za-z]", value)) >= 8
        and not any(word in lowered for word in BAD_TITLE_WORDS)
        and not lowered.startswith(("http://", "https://"))
    )


def slugify(value: str, max_len: int = 180) -> str:
    value = value.replace("&", " and ")
    value = re.sub(r"[^A-Za-z0-9._ -]+", "", value)
    value = re.sub(r"\s+", "_", value.strip())
    value = re.sub(r"_+", "_", value).strip("._-")
    return value[:max_len] or "document"


def title_key(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"\b(preprint|accepted manuscript|author manuscript|final|revised)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value


class TitleHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.capture = None
        self.title = []
        self.h1 = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"title", "h1"}:
            self.capture = tag.lower()

    def handle_endtag(self, tag):
        if tag.lower() == self.capture:
            self.capture = None

    def handle_data(self, data):
        if self.capture == "title":
            self.title.append(data)
        elif self.capture == "h1":
            self.h1.append(data)


def title_from_pdf(path: Path) -> str | None:
    try:
        import fitz

        document = fitz.open(str(path))
        metadata = clean_title((document.metadata or {}).get("title") or "")
        if valid_title(metadata):
            return metadata
        if len(document):
            lines = [clean_title(line) for line in (document[0].get_text("text") or "").splitlines()]
            for line in lines[:25]:
                if valid_title(line) and len(line.split()) >= 4:
                    return line
    except Exception:
        pass
    try:
        from pypdf import PdfReader

        metadata = PdfReader(str(path)).metadata
        title = clean_title(str(getattr(metadata, "title", "") or ""))
        return title if valid_title(title) else None
    except Exception:
        return None


def title_from_docx(path: Path) -> str | None:
    try:
        with zipfile.ZipFile(path) as archive:
            if "docProps/core.xml" in archive.namelist():
                root = ElementTree.fromstring(archive.read("docProps/core.xml"))
                for element in root.iter():
                    if element.tag.endswith("}title") and element.text:
                        title = clean_title(element.text)
                        if valid_title(title):
                            return title
            root = ElementTree.fromstring(archive.read("word/document.xml"))
            for paragraph in root.iter():
                if not paragraph.tag.endswith("}p"):
                    continue
                text = clean_title("".join(node.text or "" for node in paragraph.iter() if node.tag.endswith("}t")))
                if valid_title(text) and len(text.split()) >= 4:
                    return text
    except Exception:
        return None
    return None


def title_from_html(path: Path) -> str | None:
    try:
        parser = TitleHTMLParser()
        parser.feed(path.read_text(encoding="utf-8", errors="ignore"))
        for value in (" ".join(parser.h1), " ".join(parser.title)):
            value = clean_title(value)
            if valid_title(value):
                return value
    except Exception:
        return None
    return None


def extract_title(path: Path) -> str:
    suffix = path.suffix.lower()
    title = None
    if suffix == ".pdf":
        title = title_from_pdf(path)
    elif suffix == ".docx":
        title = title_from_docx(path)
    elif suffix in {".html", ".htm"}:
        title = title_from_html(path)
    fallback = clean_title(path.stem.replace("_", " ").replace("-", " "))
    return title or fallback or path.stem


def pdf_preflight(path: Path) -> dict[str, Any]:
    if path.suffix.lower() != ".pdf":
        return {"status": "not_applicable"}
    with path.open("rb") as handle:
        signature = handle.read(5)
    if signature != b"%PDF-":
        return {"status": "review_needed", "reason": "missing_pdf_signature"}
    try:
        import fitz

        document = fitz.open(str(path))
        if document.needs_pass:
            return {"status": "failed", "reason": "password_protected"}
        return {"status": "accepted", "page_count": len(document)}
    except Exception as error:
        return {"status": "review_needed", "reason": f"pdf_parser_warning:{error}"}


def discover(input_path: Path) -> tuple[list[Path], list[Path]]:
    files = [input_path] if input_path.is_file() else sorted(path for path in input_path.rglob("*") if path.is_file())
    supported, skipped = [], []
    for path in files:
        (supported if path.suffix.lower() in SUPPORTED_EXTENSIONS else skipped).append(path)
    return supported, skipped


def work_candidates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = []
    for left_index, left in enumerate(records):
        for right in records[left_index + 1:]:
            if left["work_id"] == right["work_id"]:
                continue
            ratio = SequenceMatcher(None, left["title_key"], right["title_key"]).ratio()
            if ratio >= 0.92:
                candidates.append(
                    {
                        "left_document_id": left["document_id"],
                        "right_document_id": right["document_id"],
                        "left_title": left["title"],
                        "right_title": right["title"],
                        "similarity": round(ratio, 4),
                        "status": "review_needed",
                    }
                )
    return candidates


def ingest(
    input_path: Path,
    corpus: Path,
    rename_mode: str = "title",
    format_policy: str = "prefer-pdf",
    quarantine_duplicates: bool = True,
) -> dict[str, int]:
    supported, skipped = discover(input_path)
    (corpus / "logs").mkdir(parents=True, exist_ok=True)
    (corpus / "manifests").mkdir(parents=True, exist_ok=True)
    (corpus / "sources").mkdir(parents=True, exist_ok=True)
    (corpus / "pdfs").mkdir(parents=True, exist_ok=True)
    (corpus / "quarantine" / "duplicates").mkdir(parents=True, exist_ok=True)
    (corpus / "quarantine" / "unreadable").mkdir(parents=True, exist_ok=True)
    (corpus / "logs" / "skipped_unsupported_files.txt").write_text(
        "".join(f"{path}\n" for path in skipped), encoding="utf-8"
    )

    previous = {record.get("sha256"): record for record in load_manifest(corpus) if record.get("sha256")}
    seen: dict[str, Path] = {}
    records: list[dict[str, Any]] = []
    duplicates = []
    for path in supported:
        digest = sha256_file(path)
        if digest in seen:
            duplicate = {
                "sha256": digest,
                "canonical_source": str(seen[digest]),
                "duplicate_source": str(path),
                "action": "not_copied",
                "created_at": now(),
            }
            if quarantine_duplicates and corpus in path.parents:
                target = corpus / "quarantine" / "duplicates" / path.name
                if target.exists():
                    target = target.with_name(f"{target.stem}_{digest[:8]}{target.suffix}")
                shutil.move(str(path), target)
                duplicate.update({"action": "quarantined", "quarantine_path": str(target)})
            duplicates.append(duplicate)
            continue
        seen[digest] = path
        title = extract_title(path)
        key = title_key(title) or digest
        work_id = f"work_{hashlib.sha256(key.encode()).hexdigest()[:16]}"
        document_id = f"doc_{digest[:16]}"
        file_format = "html" if path.suffix.lower() in {".html", ".htm"} else path.suffix.lower().lstrip(".")
        name_stem = slugify(title) if rename_mode == "title" else slugify(path.stem)
        destination_dir = corpus / ("pdfs" if file_format == "pdf" else f"sources/{file_format}")
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"{name_stem}.{file_format}"
        if destination.exists() and sha256_file(destination) != digest:
            destination = destination_dir / f"{name_stem}_{digest[:8]}.{file_format}"
        if path.resolve() != destination.resolve():
            if destination.exists() and sha256_file(destination) == digest:
                if corpus in path.parents:
                    quarantine = corpus / "quarantine" / "duplicates" / path.name
                    if quarantine.exists():
                        quarantine = quarantine.with_name(f"{quarantine.stem}_{digest[:8]}{quarantine.suffix}")
                    shutil.move(str(path), quarantine)
                    duplicates.append(
                        {
                            "sha256": digest,
                            "canonical_source": str(destination),
                            "duplicate_source": str(path),
                            "action": "quarantined",
                            "quarantine_path": str(quarantine),
                            "created_at": now(),
                        }
                    )
            elif corpus in path.parents:
                shutil.move(str(path), destination)
            else:
                shutil.copy2(path, destination)

        record = dict(previous.get(digest, {}))
        record.update(
            {
                "document_id": document_id,
                "work_id": work_id,
                "sha256": digest,
                "title": title,
                "title_key": key,
                "format": file_format,
                "source_path": str(path),
                "canonical_path": str(destination.relative_to(corpus)),
                "file_name": destination.name,
                "file_size": destination.stat().st_size,
                "selected_for_extraction": True,
                "extractable": True,
                "selection_reason": "only_representation",
                "created_at": record.get("created_at", now()),
            }
        )
        preflight = pdf_preflight(destination)
        record["preflight"] = preflight
        if preflight.get("status") == "failed":
            record["extractable"] = False
            record["selected_for_extraction"] = False
            quarantine = corpus / "quarantine" / "unreadable" / destination.name
            if quarantine.exists():
                quarantine = quarantine.with_name(f"{quarantine.stem}_{digest[:8]}{quarantine.suffix}")
            shutil.move(str(destination), quarantine)
            record["canonical_path"] = str(quarantine.relative_to(corpus))
            update_stage(record, "extraction", "failed", error=preflight.get("reason"))
        update_stage(record, "ingestion", "complete")
        records.append(record)

    by_work: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_work.setdefault(record["work_id"], []).append(record)
    if format_policy == "prefer-pdf":
        for representations in by_work.values():
            eligible = [item for item in representations if item.get("extractable", True)]
            if not eligible:
                continue
            best_rank = min(FORMAT_RANK[item["format"]] for item in eligible)
            chosen = [item for item in eligible if FORMAT_RANK[item["format"]] == best_rank]
            for record in representations:
                selected = record in chosen and record.get("extractable", True)
                record["selected_for_extraction"] = selected
                record["selection_reason"] = (
                    "preferred_format" if selected else f"alternate_of:{chosen[0]['document_id']}"
                )
                if not selected and record.get("extractable", True):
                    update_stage(record, "extraction", "skipped", reason="alternate_representation")

    save_manifest(corpus, records)
    write_jsonl(corpus / "manifests" / "duplicates.jsonl", duplicates)
    write_jsonl(corpus / "manifests" / "work_match_candidates.jsonl", work_candidates(records))
    return {
        "supported": len(supported),
        "documents": len(records),
        "works": len(by_work),
        "duplicates": len(duplicates),
        "skipped": len(skipped),
        "selected": sum(bool(record["selected_for_extraction"]) for record in records),
    }
