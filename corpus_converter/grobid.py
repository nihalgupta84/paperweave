"""Optional GROBID scholarly metadata and bibliography integration."""

from __future__ import annotations

import logging
import re
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from .io import read_json, write_json
from .manifest import load_manifest, record_error, save_manifest, update_stage
from .validation import validate_document, validate_work

logger = logging.getLogger(__name__)


def _text(element: ElementTree.Element | None) -> str:
    return " ".join("".join(element.itertext()).split()) if element is not None else ""


def _identifier(element: ElementTree.Element, kind: str) -> str | None:
    for value in element.findall(".//{*}idno"):
        if value.attrib.get("type", "").casefold() == kind.casefold() and _text(value):
            return _text(value)
    return None


def _authors(element: ElementTree.Element) -> list[str]:
    values: list[str] = []
    for author in element.findall(".//{*}author"):
        person = author.find(".//{*}persName")
        if person is None:
            continue
        forenames = " ".join(_text(item) for item in person.findall("{*}forename") if _text(item))
        surname = _text(person.find("{*}surname"))
        name = " ".join(item for item in (forenames, surname) if item).strip()
        if name and name not in values:
            values.append(name)
    return values


def parse_tei(xml: bytes | str) -> dict[str, Any]:
    """Parse GROBID TEI into conservative metadata and bibliography records."""
    root = ElementTree.fromstring(xml)
    header = root.find(".//{*}teiHeader") or root
    title = _text(header.find(".//{*}titleStmt/{*}title"))
    date = header.find(".//{*}publicationStmt/{*}date")
    if date is None:
        date = header.find(".//{*}sourceDesc//{*}date")
    date_value = (date.attrib.get("when", "") if date is not None else "") or _text(date)
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", date_value)

    references: list[dict[str, Any]] = []
    for index, item in enumerate(root.findall(".//{*}listBibl/{*}biblStruct"), start=1):
        title_value = _text(item.find(".//{*}analytic/{*}title")) or _text(item.find(".//{*}monogr/{*}title"))
        ref_date = item.find(".//{*}date")
        ref_date_value = (ref_date.attrib.get("when", "") if ref_date is not None else "") or _text(ref_date)
        ref_year = re.search(r"\b(19\d{2}|20\d{2})\b", ref_date_value)
        references.append(
            {
                "index": index,
                "raw": _text(item),
                "parsed_title": title_value or None,
                "parsed_authors": _authors(item),
                "parsed_year": int(ref_year.group(1)) if ref_year else None,
                "doi": _identifier(item, "DOI"),
                "arxiv_id": _identifier(item, "arXiv"),
                "source": "grobid_tei",
            }
        )

    return {
        "title": title or None,
        "authors": _authors(header),
        "year": int(year_match.group(1)) if year_match else None,
        "doi": _identifier(header, "DOI"),
        "arxiv_id": _identifier(header, "arXiv"),
        "references": references,
    }


class GrobidAdapter:
    """Small standard-library client for a local or remote GROBID service."""

    def __init__(self, base_url: str = "http://127.0.0.1:8070", timeout: float = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def probe(self) -> tuple[bool, str | None]:
        """Check if the GROBID service is alive."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/isalive")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return True, None
            return False, f"GROBID returned status {resp.status}"
        except (OSError, urllib.error.URLError) as error:
            return False, f"GROBID service unavailable: {error}"

    def process_fulltext(self, pdf_path: Path) -> bytes:
        """Submit one PDF to ``processFulltextDocument`` and return TEI XML."""
        boundary = f"paperweave-{uuid.uuid4().hex}"
        safe_name = pdf_path.name.replace('"', "_").replace("\r", "_").replace("\n", "_")
        prefix = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="input"; filename="{safe_name}"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode()
        suffix = f"\r\n--{boundary}--\r\n".encode()
        request = urllib.request.Request(
            f"{self.base_url}/api/processFulltextDocument",
            data=prefix + pdf_path.read_bytes() + suffix,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/xml"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            if response.status != 200:
                raise RuntimeError(f"GROBID returned HTTP {response.status}")
            payload = response.read()
        ElementTree.fromstring(payload)
        return payload

    def extract_fulltext(self, pdf_path: Path) -> tuple[bytes, dict[str, Any]]:
        """Return raw TEI and parsed scholarly metadata for a PDF."""
        xml = self.process_fulltext(pdf_path)
        return xml, parse_tei(xml)


def _resolve_pdf(corpus: Path, record: dict[str, Any]) -> Path | None:
    value = record.get("canonical_path") or record.get("pdf_path") or record.get("target_path")
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else corpus / path


def _fill_missing(target: dict[str, Any], metadata: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    conflicts: dict[str, Any] = {}
    for field in fields:
        incoming = metadata.get(field)
        existing = target.get(field)
        if not incoming:
            continue
        if not existing:
            target[field] = incoming
        elif existing != incoming:
            conflicts[field] = {"existing": existing, "grobid": incoming}
    return conflicts


def enrich_corpus_with_grobid(
    corpus: Path,
    base_url: str = "http://127.0.0.1:8070",
    force: bool = False,
    strict: bool = False,
) -> dict[str, Any]:
    """Enrich selected PDFs without overwriting conflicting canonical metadata."""
    adapter = GrobidAdapter(base_url)
    alive, reason = adapter.probe()
    if not alive:
        if strict:
            raise RuntimeError(reason)
        return {"available": False, "processed": 0, "skipped": 0, "failed": 0, "reason": reason}

    records = load_manifest(corpus)
    processed = skipped = failed = 0
    for record in records:
        if record.get("format") != "pdf" or not record.get("selected_for_extraction", True):
            continue
        document_id = record.get("document_id")
        pdf_path = _resolve_pdf(corpus, record)
        if not document_id or pdf_path is None or not pdf_path.is_file():
            failed += 1
            record_error(record, "grobid", "canonical PDF is missing")
            continue
        raw_dir = corpus / "raw" / "grobid" / document_id
        metadata_path = raw_dir / "metadata.json"
        if metadata_path.exists() and not force:
            skipped += 1
            update_stage(record, "grobid", "complete", metadata_path=str(metadata_path))
            continue
        try:
            xml, metadata = adapter.extract_fulltext(pdf_path)
            raw_dir.mkdir(parents=True, exist_ok=True)
            (raw_dir / "fulltext.tei.xml").write_bytes(xml)
            conflicts: dict[str, Any] = {
                "manifest": _fill_missing(record, metadata, ("title", "authors", "year", "doi", "arxiv_id"))
            }

            document_path = corpus / "papers" / document_id / "document.json"
            document = read_json(document_path, {})
            if document:
                conflicts["document"] = _fill_missing(
                    document, metadata, ("title", "authors", "year", "doi", "arxiv_id")
                )
                validate_document(document)
                write_json(document_path, document)

            work_path = corpus / "records" / record.get("work_id", "") / "work.json"
            work = read_json(work_path, {})
            if work:
                conflicts["work"] = _fill_missing(work, metadata, ("title", "authors", "year", "doi", "arxiv_id"))
                validate_work(work)
                write_json(work_path, work)
                grobid_references_path = work_path.parent / "grobid_references.json"
                existing_references = read_json(grobid_references_path, {}).get("references", [])
                combined: dict[str, dict[str, Any]] = {}
                for reference in [*existing_references, *metadata["references"]]:
                    reference = {**reference, "document_id": reference.get("document_id", document_id)}
                    key = (
                        reference.get("doi")
                        or reference.get("arxiv_id")
                        or reference.get("parsed_title")
                        or reference.get("raw")
                    )
                    if key:
                        combined[str(key).casefold()] = reference
                write_json(
                    grobid_references_path,
                    {"work_id": work.get("work_id"), "references": list(combined.values())},
                )

            write_json(metadata_path, {**metadata, "conflicts": conflicts, "source_pdf": str(pdf_path)})
            update_stage(record, "grobid", "complete", metadata_path=str(metadata_path))
            processed += 1
        except Exception as error:
            logger.warning("GROBID failed for %s: %s", pdf_path, error)
            record_error(record, "grobid", error)
            failed += 1
    save_manifest(corpus, records)
    return {"available": True, "processed": processed, "skipped": skipped, "failed": failed}
