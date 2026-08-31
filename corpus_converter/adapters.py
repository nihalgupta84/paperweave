import hashlib
import re
import shutil
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

from .io import write_json, write_jsonl
from .manifest import load_manifest, now, record_error, save_manifest, update_stage
from .quality import assess_document


def block_id(document_id: str, index: int, text: str, block_type: str) -> str:
    value = f"{document_id}\0{index}\0{block_type}\0{text}".encode()
    return f"blk_{hashlib.sha256(value).hexdigest()[:20]}"


def normalized_block(document_id: str, index: int, text: str, block_type: str, level, parser: str):
    return {
        "block_id": block_id(document_id, index, text, block_type),
        "document_id": document_id,
        "type": block_type,
        "heading_level": level,
        "page_index": None,
        "section_path": [],
        "text": text.strip(),
        "bbox": None,
        "asset_path": None,
        "source": {
            "parser": parser,
            "parser_version": "stdlib",
            "source_file": None,
            "source_index": index,
        },
    }


def parse_docx(path: Path, document_id: str, assets_dir: Path | None = None) -> list[dict]:
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
        media = [name for name in archive.namelist() if name.startswith("word/media/") and not name.endswith("/")]
        extracted_assets = []
        if assets_dir and media:
            assets_dir.mkdir(parents=True, exist_ok=True)
            for name in media:
                data = archive.read(name)
                source_name = Path(name).name
                destination_name = f"{Path(source_name).stem}_{hashlib.sha256(data).hexdigest()[:10]}{Path(source_name).suffix.lower()}"
                destination = assets_dir / destination_name
                if not destination.exists():
                    destination.write_bytes(data)
                extracted_assets.append(f"assets/{destination_name}")
    blocks = []
    for paragraph in root.iter():
        if not paragraph.tag.endswith("}p"):
            continue
        text = "".join(node.text or "" for node in paragraph.iter() if node.tag.endswith("}t"))
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        style = next((node.attrib for node in paragraph.iter() if node.tag.endswith("}pStyle")), {})
        style_value = next(iter(style.values()), "")
        match = re.search(r"heading\s*([1-6])", style_value, re.I)
        level = int(match.group(1)) if match else None
        block_type = "title" if level else "paragraph"
        blocks.append(normalized_block(document_id, len(blocks), text, block_type, level, "docx"))
    for asset_path in extracted_assets:
        block = normalized_block(document_id, len(blocks), "Embedded DOCX image", "image", None, "docx")
        block["asset_path"] = asset_path
        blocks.append(block)
    return blocks


class ContentHTMLParser(HTMLParser):
    BLOCK_TAGS = {"title", "h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "figcaption"}

    def __init__(self):
        super().__init__()
        self.active = None
        self.buffer = []
        self.blocks = []
        self.images = []
        self.ignored_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "style", "nav"}:
            self.ignored_depth += 1
        elif not self.ignored_depth and tag in self.BLOCK_TAGS:
            self.flush()
            self.active = tag
        elif not self.ignored_depth and tag == "img":
            values = dict(attrs)
            if values.get("src"):
                self.images.append((values["src"], values.get("alt", "HTML image")))

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style", "nav"} and self.ignored_depth:
            self.ignored_depth -= 1
        elif tag == self.active:
            self.flush()

    def handle_data(self, data):
        if self.active and not self.ignored_depth:
            self.buffer.append(data)

    def flush(self):
        if self.active:
            text = re.sub(r"\s+", " ", " ".join(self.buffer)).strip()
            if text:
                self.blocks.append((self.active, text))
        self.active = None
        self.buffer = []


def parse_html(
    path: Path,
    document_id: str,
    assets_dir: Path | None = None,
    resource_root: Path | None = None,
) -> list[dict]:
    parser = ContentHTMLParser()
    parser.feed(path.read_text(encoding="utf-8", errors="ignore"))
    parser.flush()
    blocks = []
    for tag, text in parser.blocks:
        level = int(tag[1]) if re.fullmatch(r"h[1-6]", tag) else (1 if tag == "title" else None)
        block_type = "title" if level else "paragraph"
        blocks.append(normalized_block(document_id, len(blocks), text, block_type, level, "html"))
    if assets_dir:
        assets_dir.mkdir(parents=True, exist_ok=True)
        source_root = (resource_root or path.parent).resolve()
        for source_value, alt in parser.images:
            if re.match(r"^(?:https?:|data:|//)", source_value, re.I):
                continue
            source = (source_root / source_value).resolve()
            if not source.is_file() or not source.is_relative_to(source_root):
                continue
            digest = hashlib.sha256(source.read_bytes()).hexdigest()[:10]
            destination = assets_dir / f"{source.stem}_{digest}{source.suffix.lower()}"
            if not destination.exists():
                shutil.copy2(source, destination)
            block = normalized_block(document_id, len(blocks), alt or "HTML image", "image", None, "html")
            block["asset_path"] = f"assets/{destination.name}"
            blocks.append(block)
    return blocks


def markdown_from_blocks(blocks: list[dict]) -> str:
    output = []
    for block in blocks:
        if block.get("asset_path"):
            output.append(f"![{block['text']}]({block['asset_path']})")
        elif block["heading_level"]:
            output.append(f"{'#' * block['heading_level']} {block['text']}")
        else:
            output.append(block["text"])
        output.append("")
    return "\n".join(output)


def normalize_non_pdf(corpus: Path, force: bool = False) -> dict[str, int]:
    records = load_manifest(corpus)
    counts = {"done": 0, "skipped": 0, "failed": 0}
    for record in records:
        if not record.get("selected_for_extraction") or record.get("format") == "pdf":
            continue
        document_id = record["document_id"]
        paper_dir = corpus / "papers" / document_id
        if (paper_dir / ".done").exists() and not force:
            counts["skipped"] += 1
            update_stage(record, "normalization", "complete", parser=record["format"])
            continue
        try:
            source = corpus / record["canonical_path"]
            assets_dir = paper_dir / "assets"
            blocks = (
                parse_docx(source, document_id, assets_dir)
                if record["format"] == "docx"
                else parse_html(
                    source,
                    document_id,
                    assets_dir,
                    Path(record.get("source_path", source)).parent,
                )
            )
            if not blocks:
                raise ValueError("No document blocks extracted")
            paper_dir.mkdir(parents=True, exist_ok=True)
            write_jsonl(paper_dir / "blocks.jsonl", blocks)
            (paper_dir / "paper.md").write_text(markdown_from_blocks(blocks), encoding="utf-8")
            document = {
                "document_id": document_id,
                "work_id": record["work_id"],
                "sha256": record["sha256"],
                "format": record["format"],
                "version": "unknown",
                "title": record["title"],
                "authors": [],
                "doi": None,
                "arxiv_id": None,
                "source_path": record["canonical_path"],
                "parser": {"name": record["format"], "version": "stdlib", "processed_at": now()},
                "block_count": len(blocks),
                "asset_count": sum(block.get("asset_path") is not None for block in blocks),
            }
            write_json(paper_dir / "document.json", document)
            quality = assess_document(paper_dir)
            (paper_dir / ".done").write_text("done\n", encoding="utf-8")
            update_stage(record, "extraction", "complete", parser=record["format"])
            update_stage(record, "normalization", "complete", quality_status=quality["status"])
            counts["done"] += 1
        except Exception as error:
            record_error(record, "normalization", error)
            counts["failed"] += 1
    save_manifest(corpus, records)
    return counts
