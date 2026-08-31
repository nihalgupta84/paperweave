#!/usr/bin/env bash
set -euo pipefail

CORPUS_DIR=""
BACKEND="pipeline"
METHOD="auto"
DEVICE="auto"
FORCE="0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --corpus-dir)
      CORPUS_DIR="$2"
      shift 2
      ;;
    --backend)
      BACKEND="$2"
      shift 2
      ;;
    --method)
      METHOD="$2"
      shift 2
      ;;
    --device)
      DEVICE="$2"
      shift 2
      ;;
    --force)
      FORCE="1"
      shift
      ;;
    *)
      echo "Unknown argument: $1"
      exit 1
      ;;
  esac
done

if [[ -z "$CORPUS_DIR" ]]; then
  echo "Usage:"
  echo "  bash scripts/03_run_mineru_batch.sh --corpus-dir <target_corpus_dir> [--backend pipeline] [--method auto] [--device auto|gpu|cpu] [--force]"
  exit 1
fi

RAW_DIR="$CORPUS_DIR/pdfs"
MINERU_RAW="$CORPUS_DIR/raw/mineru"
LOGS="$CORPUS_DIR/logs"

if [[ ! -d "$RAW_DIR" && -d "$CORPUS_DIR/raw_pdfs" ]]; then
  echo "Using legacy PDF path: $CORPUS_DIR/raw_pdfs"
  RAW_DIR="$CORPUS_DIR/raw_pdfs"
fi

mkdir -p "$MINERU_RAW" "$LOGS"

if [[ ! -d "$RAW_DIR" ]]; then
  echo "ERROR: PDF directory not found: $RAW_DIR"
  exit 2
fi

PDF_COUNT=$(find "$RAW_DIR" -type f \( -iname "*.pdf" -o -iname "*.PDF" \) | wc -l)
if [[ "$PDF_COUNT" -eq 0 ]]; then
  echo "No selected PDFs found in $RAW_DIR. MinerU is not needed for DOCX/HTML-only input."
  exit 0
fi

if ! command -v mineru >/dev/null 2>&1; then
  echo "ERROR: mineru command not found. Activate mineru environment first."
  exit 4
fi

if [[ "$FORCE" == "0" ]]; then
  MD_COUNT=$(find "$MINERU_RAW" -name "*.md" 2>/dev/null | wc -l || true)
  if [[ "$MD_COUNT" -ge "$PDF_COUNT" ]]; then
    echo "MinerU raw output already appears complete."
    echo "PDF count: $PDF_COUNT"
    echo "Markdown count: $MD_COUNT"
    echo "Use --force to rerun."
    python "$SCRIPT_DIR/06_build_knowledge.py" reconcile-mineru --corpus "$CORPUS_DIR"
    exit 0
  fi
fi

if [[ "$DEVICE" == "cpu" ]]; then
  export CUDA_VISIBLE_DEVICES=""
  echo "Running in CPU mode. CUDA_VISIBLE_DEVICES is empty."
elif [[ "$DEVICE" == "gpu" ]]; then
  python "$(dirname "$0")/00_check_system.py" --require-gpu
else
  echo "Running in auto device mode."
  python "$(dirname "$0")/00_check_system.py" || true
fi

LOG_FILE="$LOGS/mineru_batch_$(date +%F_%H%M%S).log"

echo "Corpus dir: $CORPUS_DIR"
echo "Raw PDFs: $RAW_DIR"
echo "MinerU raw output: $MINERU_RAW"
echo "PDF count: $PDF_COUNT"
echo "Backend: $BACKEND"
echo "Method: $METHOD"
echo "Device: $DEVICE"
echo "Log: $LOG_FILE"
echo

set +e
mineru \
  -p "$RAW_DIR" \
  -o "$MINERU_RAW" \
  -b "$BACKEND" \
  -m "$METHOD" \
  2>&1 | tee "$LOG_FILE"
MINERU_EXIT=${PIPESTATUS[0]}
set -e

python "$SCRIPT_DIR/06_build_knowledge.py" reconcile-mineru --corpus "$CORPUS_DIR"

COMPLETE_COUNT=$(python - "$CORPUS_DIR/manifests/documents.jsonl" <<'PY'
import json, sys
count = 0
with open(sys.argv[1], encoding="utf-8") as handle:
    for line in handle:
        record = json.loads(line)
        count += record.get("stages", {}).get("mineru", {}).get("status") == "complete"
print(count)
PY
)

if [[ "$MINERU_EXIT" -ne 0 && "$COMPLETE_COUNT" -eq 0 ]]; then
  echo "ERROR: MinerU failed and no documents completed. Exit code: $MINERU_EXIT"
  exit "$MINERU_EXIT"
elif [[ "$MINERU_EXIT" -ne 0 ]]; then
  echo "WARNING: MinerU returned $MINERU_EXIT, but $COMPLETE_COUNT document(s) completed; failed documents remain isolated in the manifest."
fi

echo
echo "MinerU complete."
echo "Markdown count:"
find "$MINERU_RAW" -name "*.md" | wc -l
