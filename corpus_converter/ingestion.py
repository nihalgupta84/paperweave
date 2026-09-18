"""Discovery, deduplication, identification, renaming, and staging of scholarly documents."""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import zipfile
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from .hashing import sha256_file
from .io import read_jsonl, write_jsonl
from .manifest import load_manifest, now, save_manifest, update_stage

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".html", ".htm"}
FORMAT_RANK = {"pdf": 0, "docx": 1, "html": 2}
BAD_TITLE_WORDS = {"microsoft word", "untitled", "download", "index"}


def clean_title(value: str) -> str:
    """Normalize and clean a title string."""
    value = re.sub(r"[\r\n\t]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" .,:;|-_")
    return value[:300]


def valid_title(value: str) -> bool:
    """Check if a candidate title looks like a plausible scientific title."""
    lowered = value.lower()
    return (
        8 <= len(value) <= 300
        and len(re.findall(r"[A-Za-z]", value)) >= 8
        and not any(word in lowered for word in BAD_TITLE_WORDS)
        and not lowered.startswith(("http://", "https://"))
    )


def slugify(value: str, max_len: int = 180) -> str:
    """Generate a clean filesystem-safe slug from a string."""
    value = value.replace("&", " and ")
    value = re.sub(r"[^A-Za-z0-9._ -]+", "", value)
    value = re.sub(r"\s+", "_", value.strip())
    value = re.sub(r"_+", "_", value.strip("._-"))
    return value[:max_len] or "document"


def title_key(value: str) -> str:
    """Generate a normalized key for duplicate title comparison."""
    value = value.casefold()
    value = re.sub(r"\b(preprint|accepted manuscript|author manuscript|final|revised)\b", " ", value)
    # Strip subtitle after common separators so preprint titles with added
    # subtitles (e.g. ": Development and Validation of X") match the base title.
    value = re.sub(r"\s*[:\u2014\u2013]\s+.*$", "", value)
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value


def author_surnames(authors: list) -> set[str]:
    """Extract normalized last-name set from an author list."""
    surnames: set[str] = set()
    for author in authors:
        raw = author if isinstance(author, str) else (author.get("name", "") if isinstance(author, dict) else "")
        if not raw:
            continue
        raw = re.sub(r"\b(et\s+al\.?|and)\b.*$", "", raw, flags=re.I)
        # Split on delimiters that separate distinct author names (commas, semicolons, bullets, unicode separators)
        sub_authors = re.split(r"[,;•\n\r\u2c00-\u2c5f\ufeff]+", raw)
        for sub in sub_authors:
            sub = re.sub(r"[\u4e00-\u9fff]+", " ", sub)
            parts = [p for p in re.split(r"\s+", sub.strip()) if len(p) >= 2 and p.isalpha()]
            if parts:
                surnames.add(parts[-1].casefold())
    return surnames


def is_preprint_doi(doi: str | None) -> bool:
    """Check if a DOI belongs to a known preprint server."""
    if not doi:
        return False
    doi = doi.casefold().strip()
    return any(doi.startswith(prefix) for prefix in [
        "10.21203/",   # Research Square
        "10.1101/",    # bioRxiv / medRxiv
        "10.48550/",   # arXiv
        "10.20944/",   # Preprints.org
        "10.31219/",   # OSF Preprints
        "10.26434/",   # ChemRxiv
        "10.36227/",   # TechRxiv
        "10.22541/",   # Authorea
        "10.2139/",    # SSRN
    ]) or "arxiv" in doi or "preprint" in doi or "/rs." in doi


class MetadataHTMLParser(HTMLParser):
    """HTML parser to extract title, headings, meta tags, and authors."""

    def __init__(self) -> None:
        super().__init__()
        self.capture: str | None = None
        self.title: list[str] = []
        self.h1: list[str] = []
        self.authors: list[str] = []
        self.date: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        if tag_lower in {"title", "h1"}:
            self.capture = tag_lower
        elif tag_lower == "meta":
            name = (attr_dict.get("name", "") or attr_dict.get("property", "")).casefold()
            content = attr_dict.get("content", "").strip()
            if content:
                if name in {"author", "citation_author", "dc.creator"}:
                    self.authors.append(content)
                elif name in {"citation_publication_date", "citation_date", "date", "dc.date"} and not self.date:
                    self.date = content

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == self.capture:
            self.capture = None

    def handle_data(self, data: str) -> None:
        if self.capture == "title":
            self.title.append(data)
        elif self.capture == "h1":
            self.h1.append(data)


def _open_pdf(path: Path) -> Any:
    """Open a PDF across modern ``pymupdf`` and legacy ``fitz`` imports."""
    try:
        import pymupdf

        return pymupdf.open(str(path))
    except ImportError:
        import fitz

        return fitz.open(str(path))


def title_from_pdf(path: Path) -> str | None:
    """Extract a title from PDF metadata or initial page text."""
    try:
        with _open_pdf(path) as document:
            metadata = clean_title((document.metadata or {}).get("title") or "")
            if valid_title(metadata):
                return metadata
            if len(document):
                lines = [clean_title(line) for line in (document[0].get_text("text") or "").splitlines()]
                for line in lines[:25]:
                    if valid_title(line) and len(line.split()) >= 4:
                        return line
    except Exception as e:
        logger.debug("fitz title extraction failed for %s: %s", path, e)

    try:
        from pypdf import PdfReader

        metadata = PdfReader(str(path)).metadata
        title = clean_title(str(getattr(metadata, "title", "") or ""))
        return title if valid_title(title) else None
    except Exception as e:
        logger.debug("pypdf title extraction failed for %s: %s", path, e)
        return None


def title_from_docx(path: Path) -> str | None:
    """Extract a title from DOCX metadata or first heading."""
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
    except Exception as e:
        logger.debug("docx title extraction failed for %s: %s", path, e)
        return None
    return None


def title_from_html(path: Path) -> str | None:
    """Extract a title from HTML title or h1 tags."""
    try:
        parser = MetadataHTMLParser()
        parser.feed(path.read_text(encoding="utf-8", errors="ignore"))
        for value in (" ".join(parser.h1), " ".join(parser.title)):
            value = clean_title(value)
            if valid_title(value):
                return value
    except Exception as e:
        logger.debug("html title extraction failed for %s: %s", path, e)
        return None
    return None


def extract_title(path: Path) -> str:
    """Extract or fall back to filename-derived title."""
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


def extract_year_from_filename(path: Path) -> int | None:
    """Extract a 4-digit publication year from filename patterns like (2023) or _2024_."""
    matches = re.findall(r"(?:^|[\s_\-\(\[])((?:19|20)\d{2})(?:[\s_\-\)\]]|$)", path.stem)
    if matches:
        year = int(matches[-1])
        if 1950 <= year <= 2030:
            return year
    return None


def extract_year(path: Path) -> int | None:
    """Extract publication year from document metadata, content, or filename."""
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        try:
            with _open_pdf(path) as document:
                meta = document.metadata or {}
                for field in ("creationDate", "modDate"):
                    val = meta.get(field, "")
                    match = re.search(r"(?:19|20)\d{2}", val)
                    if match:
                        y = int(match.group(0))
                        if 1950 <= y <= 2030:
                            return y
                if len(document):
                    first_text = document[0].get_text("text") or ""
                    match = re.search(r"\b(19\d{2}|20\d{2})\b", first_text[:2000])
                    if match:
                        y = int(match.group(0))
                        if 1950 <= y <= 2030:
                            return y
        except Exception:
            pass

    elif suffix == ".docx":
        try:
            with zipfile.ZipFile(path) as archive:
                if "docProps/core.xml" in archive.namelist():
                    root = ElementTree.fromstring(archive.read("docProps/core.xml"))
                    for element in root.iter():
                        if (
                            any(element.tag.endswith(tag) for tag in ("}created", "}modified", "}date"))
                            and element.text
                        ):
                            match = re.search(r"(?:19|20)\d{2}", element.text)
                            if match:
                                y = int(match.group(0))
                                if 1950 <= y <= 2030:
                                    return y
        except Exception:
            pass

    elif suffix in {".html", ".htm"}:
        try:
            parser = MetadataHTMLParser()
            parser.feed(path.read_text(encoding="utf-8", errors="ignore"))
            if parser.date:
                match = re.search(r"(?:19|20)\d{2}", parser.date)
                if match:
                    y = int(match.group(0))
                    if 1950 <= y <= 2030:
                        return y
        except Exception:
            pass

    return extract_year_from_filename(path)


def extract_authors(path: Path) -> list[str]:
    """Extract author names from document metadata."""
    suffix = path.suffix.lower()
    authors: list[str] = []

    if suffix == ".pdf":
        try:
            with _open_pdf(path) as document:
                author_str = (document.metadata or {}).get("author", "")
            if author_str:
                for part in re.split(r"[,;]|(?:\band\b)", author_str):
                    cleaned = clean_title(part)
                    if 2 <= len(cleaned) <= 100 and not any(bad in cleaned.lower() for bad in BAD_TITLE_WORDS):
                        authors.append(cleaned)
        except Exception:
            pass

    elif suffix == ".docx":
        try:
            with zipfile.ZipFile(path) as archive:
                if "docProps/core.xml" in archive.namelist():
                    root = ElementTree.fromstring(archive.read("docProps/core.xml"))
                    for element in root.iter():
                        if element.tag.endswith("}creator") and element.text:
                            for part in re.split(r"[,;]|(?:\band\b)", element.text):
                                cleaned = clean_title(part)
                                if 2 <= len(cleaned) <= 100:
                                    authors.append(cleaned)
        except Exception:
            pass

    elif suffix in {".html", ".htm"}:
        try:
            parser = MetadataHTMLParser()
            parser.feed(path.read_text(encoding="utf-8", errors="ignore"))
            for a in parser.authors:
                cleaned = clean_title(a)
                if 2 <= len(cleaned) <= 100:
                    authors.append(cleaned)
        except Exception:
            pass

    return list(dict.fromkeys(authors))


def extract_identifiers(path: Path) -> tuple[str | None, str | None]:
    """Extract DOI and arXiv identifiers from readily available document text."""
    text = ""
    try:
        if path.suffix.lower() == ".pdf":
            with _open_pdf(path) as document:
                text = "\n".join(document[index].get_text("text") or "" for index in range(min(2, len(document))))
        elif path.suffix.lower() == ".docx":
            with zipfile.ZipFile(path) as archive:
                text = " ".join(
                    node.text or ""
                    for node in ElementTree.fromstring(archive.read("word/document.xml")).iter()
                    if node.tag.endswith("}t")
                )
        elif path.suffix.lower() in {".html", ".htm"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as error:
        logger.debug("Identifier extraction failed for %s: %s", path, error)

    doi_match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", text, re.I)
    arxiv_match = re.search(r"(?:arXiv\s*:\s*|arxiv\.org/abs/)([\w.\-/]+)", text, re.I)
    doi = doi_match.group(0).rstrip(".,;)</") if doi_match else None
    arxiv_id = arxiv_match.group(1).rstrip(".,;)</") if arxiv_match else None
    return doi, arxiv_id


def pdf_preflight(path: Path) -> dict[str, Any]:
    """Perform preflight checks on a PDF file."""
    if path.suffix.lower() != ".pdf":
        return {"status": "not_applicable"}
    with path.open("rb") as handle:
        signature = handle.read(5)
    if signature != b"%PDF-":
        return {"status": "review_needed", "reason": "missing_pdf_signature"}
    try:
        with _open_pdf(path) as document:
            if document.needs_pass:
                return {"status": "failed", "reason": "password_protected"}
            return {"status": "accepted", "page_count": len(document)}
    except Exception as error:
        return {"status": "review_needed", "reason": f"pdf_parser_warning:{error}"}


def discover(input_path: Path) -> tuple[list[Path], list[Path]]:
    """Discover supported and unsupported files in input path."""
    if input_path.is_file():
        files = [input_path]
    else:
        generated_corpora = {
            marker.parent.parent.resolve() for marker in input_path.rglob("manifests/last_pipeline.json")
        }
        files = sorted(
            path
            for path in input_path.rglob("*")
            if path.is_file()
            and not any(root == path.resolve() or root in path.resolve().parents for root in generated_corpora)
        )
    supported, skipped = [], []
    for path in files:
        (supported if path.suffix.lower() in SUPPORTED_EXTENSIONS else skipped).append(path)
    return supported, skipped


def work_candidates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Find pairs of documents with very similar titles for human review.

    Uses a blocking strategy for efficiency on larger corpora.
    """
    candidates = []

    def add_candidate(left: dict[str, Any], right: dict[str, Any]) -> None:
        if left["work_id"] == right["work_id"]:
            return
        left_key = left.get("title_key") or title_key(left.get("title", ""))
        right_key = right.get("title_key") or title_key(right.get("title", ""))
        if not left_key or not right_key:
            return
        ratio = SequenceMatcher(None, left_key, right_key).ratio()
        if ratio >= 0.75:
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

    if len(records) <= 60:
        # Full pairwise comparison for small sets
        for left_index, left in enumerate(records):
            for right in records[left_index + 1 :]:
                add_candidate(left, right)
        return candidates

    # Character-trigram blocking preserves recall when a typo occurs near the
    # beginning of a title, unlike fixed-prefix blocking. A candidate must share
    # at least half of the smaller title's distinct trigrams before the more
    # expensive similarity comparison is performed.
    trigram_index: dict[str, list[int]] = defaultdict(list)
    trigram_sets: list[set[str]] = []
    for index, record in enumerate(records):
        key = record.get("title_key", "")
        grams = {key[pos : pos + 3] for pos in range(max(1, len(key) - 2))} if key else set()
        trigram_sets.append(grams)
        for gram in grams:
            trigram_index[gram].append(index)

    overlaps: Counter[tuple[int, int]] = Counter()
    for indexes in trigram_index.values():
        for left_pos, left_index in enumerate(indexes):
            for right_index in indexes[left_pos + 1 :]:
                overlaps[(left_index, right_index)] += 1

    for (left_index, right_index), overlap in overlaps.items():
        minimum = min(len(trigram_sets[left_index]), len(trigram_sets[right_index]))
        if minimum and overlap >= max(1, minimum // 2):
            add_candidate(records[left_index], records[right_index])

    return candidates


def ingest(
    input_path: Path,
    corpus: Path,
    rename_mode: str = "title",
    format_policy: str = "prefer-pdf",
    quarantine_duplicates: bool = True,
    dry_run: bool = False,
) -> dict[str, int]:
    """Ingest, deduplicate, and organize files into canonical corpus structure.

    Args:
        input_path: Source file or directory.
        corpus: Target corpus directory.
        rename_mode: 'title' or 'keep'.
        format_policy: 'prefer-pdf' or 'all'.
        quarantine_duplicates: Move byte-duplicates to quarantine if in corpus.
        dry_run: If True, do not create directories or move/copy files.
    """
    supported, skipped = discover(input_path)
    logger.info("Discovered %d supported documents, %d skipped files", len(supported), len(skipped))

    if not dry_run:
        (corpus / "logs").mkdir(parents=True, exist_ok=True)
        (corpus / "manifests").mkdir(parents=True, exist_ok=True)
        (corpus / "sources").mkdir(parents=True, exist_ok=True)
        (corpus / "pdfs").mkdir(parents=True, exist_ok=True)
        (corpus / "quarantine" / "duplicates").mkdir(parents=True, exist_ok=True)
        (corpus / "quarantine" / "unreadable").mkdir(parents=True, exist_ok=True)
        skipped_log = corpus / "logs" / "skipped_unsupported_files.txt"
        previous_skipped = (
            set(skipped_log.read_text(encoding="utf-8", errors="ignore").splitlines())
            if skipped_log.exists()
            else set()
        )
        previous_skipped.update(str(path) for path in skipped)
        skipped_log.write_text("".join(f"{path}\n" for path in sorted(previous_skipped)), encoding="utf-8")

    previous_records = load_manifest(corpus)
    previous = {record.get("sha256"): record for record in previous_records if record.get("sha256")}
    seen: dict[str, Path] = {}
    records_by_hash = {record["sha256"]: dict(record) for record in previous_records if record.get("sha256")}
    records_without_hash = [dict(record) for record in previous_records if not record.get("sha256")]
    duplicates = read_jsonl(corpus / "manifests" / "duplicates.jsonl") if not dry_run else []
    new_documents = 0

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
            if not dry_run and quarantine_duplicates and corpus in path.parents:
                target = corpus / "quarantine" / "duplicates" / path.name
                if target.exists():
                    target = target.with_name(f"{target.stem}_{digest[:8]}{target.suffix}")
                shutil.move(str(path), target)
                duplicate.update({"action": "quarantined", "quarantine_path": str(target)})
            duplicates.append(duplicate)
            continue

        existing = previous.get(digest)
        if existing:
            canonical_value = existing.get("canonical_path") or existing.get("pdf_path")
            canonical = corpus / canonical_value if canonical_value else None
            if canonical and canonical.exists():
                duplicate = {
                    "sha256": digest,
                    "canonical_source": str(canonical),
                    "duplicate_source": str(path),
                    "action": "already_ingested",
                    "created_at": now(),
                }
                if (
                    not dry_run
                    and quarantine_duplicates
                    and corpus in path.parents
                    and path.resolve() != canonical.resolve()
                ):
                    target = corpus / "quarantine" / "duplicates" / path.name
                    if target.exists():
                        target = target.with_name(f"{target.stem}_{digest[:8]}{target.suffix}")
                    shutil.move(str(path), target)
                    duplicate.update({"action": "quarantined", "quarantine_path": str(target)})
                duplicates.append(duplicate)
                seen[digest] = canonical
                continue

        seen[digest] = path
        title = extract_title(path)
        year = extract_year(path)
        authors = extract_authors(path)
        doi, arxiv_id = extract_identifiers(path)
        key = title_key(title) or digest
        scholarly_identity = (
            f"doi:{doi.casefold()}" if doi else f"arxiv:{arxiv_id.casefold()}" if arxiv_id else f"title:{key}"
        )
        work_id = f"work_{hashlib.sha256(scholarly_identity.encode()).hexdigest()[:16]}"
        document_id = f"doc_{digest[:16]}"
        file_format = "html" if path.suffix.lower() in {".html", ".htm"} else path.suffix.lower().lstrip(".")
        name_stem = slugify(title) if rename_mode == "title" else slugify(path.stem)
        destination_dir = corpus / ("pdfs" if file_format == "pdf" else f"sources/{file_format}")

        destination = destination_dir / f"{name_stem}.{file_format}"
        if not dry_run:
            destination_dir.mkdir(parents=True, exist_ok=True)
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

        record = dict(existing or {})
        record.update(
            {
                "document_id": document_id,
                "work_id": work_id,
                "sha256": digest,
                "title": title,
                "title_key": key,
                "year": year,
                "authors": authors,
                "doi": doi,
                "arxiv_id": arxiv_id,
                "format": file_format,
                "source_path": str(path),
                "canonical_path": str(destination.relative_to(corpus)),
                "file_name": destination.name,
                "file_size": destination.stat().st_size if not dry_run else path.stat().st_size,
                "selected_for_extraction": True,
                "extractable": True,
                "selection_reason": "only_representation",
                "created_at": record.get("created_at", now()),
            }
        )

        preflight = pdf_preflight(path if dry_run else destination)
        record["preflight"] = preflight
        if preflight.get("status") == "failed":
            record["extractable"] = False
            record["selected_for_extraction"] = False
            if not dry_run:
                quarantine = corpus / "quarantine" / "unreadable" / destination.name
                if quarantine.exists():
                    quarantine = quarantine.with_name(f"{quarantine.stem}_{digest[:8]}{quarantine.suffix}")
                shutil.move(str(destination), quarantine)
                record["canonical_path"] = str(quarantine.relative_to(corpus))
            update_stage(record, "extraction", "failed", error=preflight.get("reason"))

        update_stage(record, "ingestion", "complete")
        records_by_hash[digest] = record
        new_documents += int(existing is None)

    records = records_without_hash + list(records_by_hash.values())

    # Phase A: Reconcile representations that share an exact normalized title
    # unless they carry conflicting scholarly identifiers.  Existing work IDs
    # win so incremental ingestion never strands previously generated records.
    previous_hashes = set(previous)
    title_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        title_groups[record.get("title_key") or title_key(record.get("title", ""))].append(record)
    for group_key, representations in title_groups.items():
        if not group_key or len(representations) < 2:
            continue
        dois = {str(record["doi"]).casefold() for record in representations if record.get("doi")}
        arxiv_ids = {str(record["arxiv_id"]).casefold() for record in representations if record.get("arxiv_id")}
        non_preprint_dois = {d for d in dois if not is_preprint_doi(d)}
        if len(non_preprint_dois) > 1 or len(arxiv_ids) > 1:
            continue
        existing_work_ids = [record["work_id"] for record in representations if record.get("sha256") in previous_hashes]
        canonical_work_id = existing_work_ids[0] if existing_work_ids else representations[0]["work_id"]
        for record in representations:
            record["work_id"] = canonical_work_id

    # Phase B: Auto-merge near-duplicate titles using fuzzy matching + author
    # overlap verification.  This catches preprint vs. journal pairs that have
    # different DOIs and slight subtitle variations.
    def _fuzzy_auto_merge(records: list[dict[str, Any]]) -> None:
        """Union-find merge of records whose titles are similar AND share author surnames."""
        n = len(records)
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        keys = [r.get("title_key") or title_key(r.get("title", "")) for r in records]
        for i in range(n):
            for j in range(i + 1, n):
                if find(i) == find(j):
                    continue
                ki, kj = keys[i], keys[j]
                if not ki or not kj:
                    continue
                ratio = SequenceMatcher(None, ki, kj).ratio()
                if ratio < 0.75:
                    continue
                # Do not merge records that carry conflicting published journal DOIs or arXiv IDs.
                # Preprint DOIs paired with published DOIs are expected for preprint/journal pairs.
                doi_i = (records[i].get("doi") or "").casefold()
                doi_j = (records[j].get("doi") or "").casefold()
                if doi_i and doi_j and doi_i != doi_j:
                    if not (is_preprint_doi(doi_i) or is_preprint_doi(doi_j)):
                        continue
                arxiv_i = (records[i].get("arxiv_id") or "").casefold()
                arxiv_j = (records[j].get("arxiv_id") or "").casefold()
                if arxiv_i and arxiv_j and arxiv_i != arxiv_j:
                    continue
                # Require at least one shared author surname (when both have authors)
                left_names = author_surnames(records[i].get("authors") or [])
                right_names = author_surnames(records[j].get("authors") or [])
                if left_names and right_names and not (left_names & right_names):
                    continue
                union(i, j)

        # Assign canonical work_id per group
        groups: dict[int, list[int]] = defaultdict(list)
        for i in range(n):
            groups[find(i)].append(i)
        for members in groups.values():
            if len(members) < 2:
                continue
            existing = [
                records[m]["work_id"] for m in members
                if records[m].get("sha256") in previous_hashes
            ]
            canonical = existing[0] if existing else records[members[0]]["work_id"]
            for m in members:
                records[m]["work_id"] = canonical

    _fuzzy_auto_merge(records)

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

    if not dry_run:
        save_manifest(corpus, records)
        write_jsonl(corpus / "manifests" / "duplicates.jsonl", duplicates)
        write_jsonl(corpus / "manifests" / "work_match_candidates.jsonl", work_candidates(records))

    logger.info(
        "Ingestion completed: %d documents (%d works), %d duplicates, %d selected",
        len(records),
        len(by_work),
        len(duplicates),
        sum(bool(r["selected_for_extraction"]) for r in records),
    )

    return {
        "supported": len(supported),
        "documents": len(records),
        "new_documents": new_documents,
        "works": len(by_work),
        "duplicates": len(duplicates),
        "skipped": len(skipped),
        "selected": sum(bool(record["selected_for_extraction"]) for record in records),
    }
