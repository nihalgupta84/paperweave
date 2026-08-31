#!/usr/bin/env bash
set -euo pipefail

CORPUS_DIR="${1:-}"

if [[ -z "$CORPUS_DIR" ]]; then
  echo "Usage:"
  echo "  bash scripts/99_status.sh <target_corpus_dir>"
  exit 1
fi

if [[ ! -d "$CORPUS_DIR" ]]; then
  echo "ERROR: corpus directory not found: $CORPUS_DIR"
  exit 2
fi

PDF_DIR="$CORPUS_DIR/pdfs"
MINERU_DIR="$CORPUS_DIR/raw/mineru"
MANIFEST="$CORPUS_DIR/manifests/documents.jsonl"
[[ -d "$PDF_DIR" ]] || PDF_DIR="$CORPUS_DIR/raw_pdfs"
[[ -d "$MINERU_DIR" ]] || MINERU_DIR="$CORPUS_DIR/mineru_raw"
[[ -f "$MANIFEST" ]] || MANIFEST="$CORPUS_DIR/manifests/pdf_manifest.jsonl"

echo "============================================================"
echo "Corpus status"
echo "============================================================"
echo "Corpus dir: $CORPUS_DIR"
echo

echo "Source PDFs:"
find "$PDF_DIR" -type f \( -iname "*.pdf" -o -iname "*.PDF" \) 2>/dev/null | wc -l || true

echo "Source DOCX/HTML:"
find "$CORPUS_DIR/sources" -type f \( -iname "*.docx" -o -iname "*.html" -o -iname "*.htm" \) 2>/dev/null | wc -l || true

echo "Downloaded PDFs:"
find "$CORPUS_DIR/downloaded" -type f \( -iname "*.pdf" -o -iname "*.PDF" \) 2>/dev/null | wc -l || true

echo "MinerU raw paper folders:"
find "$MINERU_DIR" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l || true

echo "MinerU raw markdown:"
find "$MINERU_DIR" -name "*.md" 2>/dev/null | wc -l || true

echo "Manifest documents:"
if [[ -f "$MANIFEST" ]]; then
  wc -l < "$MANIFEST"
else
  echo 0
fi

if [[ -f "$MANIFEST" ]]; then
  python - "$MANIFEST" <<'PY'
import json, sys
records = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8")]
print("Selected representations:")
print(sum(bool(record.get("selected_for_extraction")) for record in records))
print("Failed stages:")
print(sum(any(stage.get("status") == "failed" for stage in record.get("stages", {}).values()) for record in records))
print("Review-needed documents:")
print(sum(record.get("preflight", {}).get("status") == "review_needed" for record in records))
PY
fi

echo "Quarantined duplicates:"
find "$CORPUS_DIR/quarantine/duplicates" -type f 2>/dev/null | wc -l || true

echo "Quarantined unreadable documents:"
find "$CORPUS_DIR/quarantine/unreadable" -type f 2>/dev/null | wc -l || true

echo "Normalized documents:"
find "$CORPUS_DIR/papers" -mindepth 2 -maxdepth 2 -name ".done" 2>/dev/null | wc -l || true

echo "Normalized markdown:"
find "$CORPUS_DIR/papers" -mindepth 2 -maxdepth 2 -name "paper.md" 2>/dev/null | wc -l || true

echo "Document records:"
find "$CORPUS_DIR/papers" -mindepth 2 -maxdepth 2 -name "document.json" 2>/dev/null | wc -l || true

echo "Normalized blocks:"
find "$CORPUS_DIR/papers" -mindepth 2 -maxdepth 2 -name "blocks.jsonl" -exec cat {} + 2>/dev/null | wc -l || true

echo "Normalized assets:"
find "$CORPUS_DIR/papers" -path "*/assets/*" -type f 2>/dev/null | wc -l || true

echo "Knowledge records:"
find "$CORPUS_DIR/records" -mindepth 2 -maxdepth 2 -name "analysis.json" 2>/dev/null | wc -l || true

echo "Collections:"
find "$CORPUS_DIR/collections" -type f -name "*.md" 2>/dev/null | wc -l || true

echo "Synthesis reports:"
find "$CORPUS_DIR/synthesis" -maxdepth 1 -type f -name "*.md" 2>/dev/null | wc -l || true

echo
echo "Recent logs:"
find "$CORPUS_DIR/logs" -maxdepth 1 -type f 2>/dev/null | sort | tail -10 || true

echo "============================================================"
