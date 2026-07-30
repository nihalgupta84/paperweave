#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path


BAD_TITLE_WORDS = {
    "microsoft word",
    "untitled",
    "paper",
    "article",
    "download",
    "index",
}


def slugify(text: str, max_len: int = 180) -> str:
    text = text.strip().replace("&", "and")
    text = re.sub(r"[\n\r\t]+", " ", text)
    text = re.sub(r"[^A-Za-z0-9._ -]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace(" ", "_")
    text = re.sub(r"_+", "_", text).strip("._-")
    return text[:max_len] or "paper"


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def is_bad_title(title: str) -> bool:
    if not title:
        return True

    t = title.strip()
    low = t.lower()

    if len(t) < 8 or len(t) > 250:
        return True

    if any(w in low for w in BAD_TITLE_WORDS):
        return True

    if low.startswith("http") or "www." in low:
        return True

    if t.count("/") > 2:
        return True

    if len(re.findall(r"[A-Za-z]", t)) < 8:
        return True

    return False


def clean_title_line(line: str) -> str:
    line = re.sub(r"\s+", " ", line).strip()
    line = re.sub(r"^\d+\s+", "", line)
    return line.strip(" .,:;|-_")


def title_from_pymupdf(pdf_path: Path) -> str | None:
    try:
        import fitz

        doc = fitz.open(str(pdf_path))

        meta_title = ""
        try:
            meta_title = (doc.metadata or {}).get("title") or ""
            meta_title = clean_title_line(meta_title)
            if not is_bad_title(meta_title):
                return meta_title
        except Exception:
            pass

        if len(doc) == 0:
            return None

        page = doc[0]
        text = page.get_text("text") or ""
        lines = [clean_title_line(x) for x in text.splitlines()]
        lines = [x for x in lines if x and len(x) > 5]

        candidates = []
        for i, line in enumerate(lines[:30]):
            low = line.lower()
            if any(skip in low for skip in ["abstract", "keywords", "doi", "issn", "journal", "conference"]):
                continue
            if "@" in line:
                continue
            if len(line.split()) < 3:
                continue

            cand = line

            # Sometimes title wraps over two lines.
            if i + 1 < len(lines):
                nxt = lines[i + 1]
                if (
                    len(nxt.split()) >= 2
                    and "@" not in nxt
                    and not re.search(r"\b(university|department|institute|college)\b", nxt.lower())
                    and len(cand + " " + nxt) < 220
                ):
                    cand2 = cand + " " + nxt
                    candidates.append(cand2)

            candidates.append(cand)

        for cand in candidates:
            cand = clean_title_line(cand)
            if not is_bad_title(cand):
                return cand

    except Exception:
        return None

    return None


def title_from_pypdf(pdf_path: Path) -> str | None:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        meta = reader.metadata
        if meta and getattr(meta, "title", None):
            title = clean_title_line(str(meta.title))
            if not is_bad_title(title):
                return title
    except Exception:
        return None
    return None


def extract_title(pdf_path: Path) -> str:
    title = title_from_pymupdf(pdf_path) or title_from_pypdf(pdf_path)
    if not title or is_bad_title(title):
        title = pdf_path.stem
    return clean_title_line(title)


def collect_files(input_path: Path):
    if input_path.is_file():
        files = [input_path]
    else:
        files = sorted([p for p in input_path.rglob("*") if p.is_file()])

    pdfs = []
    skipped = []

    for p in files:
        if p.suffix.lower() == ".pdf":
            pdfs.append(p)
        else:
            skipped.append(p)

    return pdfs, skipped


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Local PDF file or folder containing PDFs.")
    parser.add_argument("--corpus-dir", required=True, help="Target corpus directory.")
    parser.add_argument("--rename-mode", choices=["title", "keep"], default="title")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    corpus_dir = Path(args.corpus_dir).expanduser().resolve()

    if not input_path.exists():
        raise SystemExit(f"Input path does not exist: {input_path}")

    raw_dir = corpus_dir / "raw_pdfs"
    logs_dir = corpus_dir / "logs"
    manifests_dir = corpus_dir / "manifests"

    raw_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)

    in_place_mode = input_path == raw_dir or (input_path.is_file() and input_path.parent == raw_dir)
    pdfs, skipped = collect_files(input_path)

    skipped_log = logs_dir / "skipped_non_pdf_files.txt"
    with skipped_log.open("w", encoding="utf-8") as f:
        for p in skipped:
            f.write(str(p) + "\n")

    manifest_path = manifests_dir / "pdf_manifest.jsonl"

    print(f"Input: {input_path}")
    print(f"PDF files found: {len(pdfs)}")
    print(f"Non-PDF files skipped: {len(skipped)}")
    print(f"Raw PDF output: {raw_dir}")

    records = []

    for idx, pdf in enumerate(pdfs, 1):
        digest = sha256_file(pdf)

        if args.rename_mode == "keep":
            title = pdf.stem
        else:
            title = extract_title(pdf)

        slug = slugify(title)
        target = raw_dir / f"{slug}.pdf"

        if in_place_mode:
            target = pdf
            print(f"[{idx}/{len(pdfs)}] IN_PLACE: {target.name}")
            action = "in_place"
        elif target.exists():
            if sha256_file(target) == digest:
                print(f"[{idx}/{len(pdfs)}] EXISTS: {target.name}")
                action = "exists_same_hash"
            else:
                short = digest[:8]
                target = raw_dir / f"{slug}_{short}.pdf"
                if target.exists() and not args.force:
                    print(f"[{idx}/{len(pdfs)}] EXISTS: {target.name}")
                    action = "exists_hash_suffix"
                else:
                    shutil.copy2(pdf, target)
                    print(f"[{idx}/{len(pdfs)}] COPY_DUP: {pdf.name} -> {target.name}")
                    action = "copied_duplicate_hash_suffix"
        else:
            shutil.copy2(pdf, target)
            print(f"[{idx}/{len(pdfs)}] COPY: {pdf.name} -> {target.name}")
            action = "copied"

        records.append(
            {
                "source_path": str(pdf),
                "target_path": str(target),
                "source_filename": pdf.name,
                "target_filename": target.name,
                "title": title,
                "slug": slug,
                "sha256": digest,
                "action": action,
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
        )

    with manifest_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print()
    print("Prepare complete.")
    print(f"Manifest: {manifest_path}")
    print(f"Skipped file log: {skipped_log}")


if __name__ == "__main__":
    main()
