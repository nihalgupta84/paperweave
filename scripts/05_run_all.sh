#!/usr/bin/env bash
set -euo pipefail

INPUT=""
CORPUS_DIR=""
REMOTE=""
DEVICE="auto"
RENAME_MODE="title"
FORMAT_POLICY="prefer-pdf"
FORCE="0"
FORCE_MINERU="0"
FORCE_NORMALIZATION="0"
FORCE_ANALYSIS="0"
TAXONOMY_PROFILE="core"
SEMANTIC_PROVIDER="deterministic"
SEMANTIC_MODEL=""
SEMANTIC_BASE_URL=""

usage() {
  cat <<'USAGE'
Usage:
  bash scripts/05_run_all.sh --input <file_or_mixed_folder> --corpus-dir <target_corpus_dir>

Options:
  --remote NAME                         rclone remote; auto-selects the only configured remote when omitted
  --device auto|gpu|cpu                 MinerU device selection
  --rename-mode title|keep               canonical source naming policy
  --format-policy prefer-pdf|all         equivalent-format selection policy
  --taxonomy-profile PROFILE             e.g. core or computer_vision/optical_flow
  --semantic-provider PROVIDER           deterministic, ollama, or openai-compatible
  --model NAME                           optional semantic model
  --base-url URL                         optional OpenAI-compatible endpoint
  --force                                rerun all expensive stages
  --force-mineru                         rerun MinerU only
  --force-normalization                  rerun normalization only
  --force-analysis                       rerun semantic analysis only
  --retry-failed                         rerun failed expensive stages
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --input)
      INPUT="$2"
      shift 2
      ;;
    --corpus-dir)
      CORPUS_DIR="$2"
      shift 2
      ;;
    --remote)
      REMOTE="$2"
      shift 2
      ;;
    --device)
      DEVICE="$2"
      shift 2
      ;;
    --rename-mode)
      RENAME_MODE="$2"
      shift 2
      ;;
    --format-policy)
      FORMAT_POLICY="$2"
      shift 2
      ;;
    --force)
      FORCE="1"
      FORCE_MINERU="1"
      FORCE_NORMALIZATION="1"
      FORCE_ANALYSIS="1"
      shift
      ;;
    --force-mineru)
      FORCE_MINERU="1"
      shift
      ;;
    --force-normalization)
      FORCE_NORMALIZATION="1"
      shift
      ;;
    --force-analysis)
      FORCE_ANALYSIS="1"
      shift
      ;;
    --retry-failed)
      FORCE_MINERU="1"
      FORCE_NORMALIZATION="1"
      FORCE_ANALYSIS="1"
      shift
      ;;
    --taxonomy-profile)
      TAXONOMY_PROFILE="$2"
      shift 2
      ;;
    --semantic-provider)
      SEMANTIC_PROVIDER="$2"
      shift 2
      ;;
    --model)
      SEMANTIC_MODEL="$2"
      shift 2
      ;;
    --base-url)
      SEMANTIC_BASE_URL="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1"
      exit 1
      ;;
  esac
done

if [[ -z "$INPUT" || -z "$CORPUS_DIR" ]]; then
  usage
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$CORPUS_DIR"/{downloaded,pdfs,papers,records,collections,synthesis,logs,manifests}
mkdir -p "$CORPUS_DIR/raw/mineru" "$CORPUS_DIR/raw/grobid"

echo "============================================================"
echo "PaperWeave"
echo "============================================================"
echo "Input: $INPUT"
echo "Corpus dir: $CORPUS_DIR"
echo "Remote: $REMOTE"
echo "Device: $DEVICE"
echo "Rename mode: $RENAME_MODE"
echo "Format policy: $FORMAT_POLICY"
echo "Force: $FORCE"
echo "Taxonomy profile: $TAXONOMY_PROFILE"
echo "Semantic provider: $SEMANTIC_PROVIDER"
echo "============================================================"

python "$SCRIPT_DIR/00_check_system.py" || true

LOCAL_INPUT="$INPUT"

if [[ "$INPUT" == *"drive.google.com"* || "$INPUT" =~ ^[A-Za-z0-9_-]{20,}$ ]]; then
  echo
  echo "[1/5] Google Drive input detected. Downloading supported documents with rclone..."
  if [[ -z "$REMOTE" ]]; then
    mapfile -t CONFIGURED_REMOTES < <(rclone listremotes | sed 's/:$//')
    if [[ "${#CONFIGURED_REMOTES[@]}" -ne 1 ]]; then
      echo "ERROR: configure exactly one rclone remote or pass --remote <name>."
      exit 2
    fi
    REMOTE="${CONFIGURED_REMOTES[0]}"
  fi
  bash "$SCRIPT_DIR/02_download_gdrive_rclone.sh" "$INPUT" "$CORPUS_DIR/downloaded" "$REMOTE"
  LOCAL_INPUT="$CORPUS_DIR/downloaded"
else
  echo
  echo "[1/5] Local input detected."
fi

echo
echo "[2/5] Preparing documents, deduplicating, and writing the manifest..."
if [[ "$FORCE" == "1" ]]; then
  python "$SCRIPT_DIR/01_prepare_inputs.py" \
    --input "$LOCAL_INPUT" \
    --corpus-dir "$CORPUS_DIR" \
    --rename-mode "$RENAME_MODE" \
    --format-policy "$FORMAT_POLICY" \
    --force
else
  python "$SCRIPT_DIR/01_prepare_inputs.py" \
    --input "$LOCAL_INPUT" \
    --corpus-dir "$CORPUS_DIR" \
    --rename-mode "$RENAME_MODE" \
    --format-policy "$FORMAT_POLICY"
fi

echo
echo "[3/5] Running MinerU batch..."
if [[ "$FORCE_MINERU" == "1" ]]; then
  bash "$SCRIPT_DIR/03_run_mineru_batch.sh" \
    --corpus-dir "$CORPUS_DIR" \
    --device "$DEVICE" \
    --force
else
  bash "$SCRIPT_DIR/03_run_mineru_batch.sh" \
    --corpus-dir "$CORPUS_DIR" \
    --device "$DEVICE"
fi

echo
echo "[4/5] Formatting MinerU output..."
if [[ "$FORCE_NORMALIZATION" == "1" ]]; then
  python "$SCRIPT_DIR/04_format_mineru_output.py" \
    --corpus-dir "$CORPUS_DIR" \
    --force
else
  python "$SCRIPT_DIR/04_format_mineru_output.py" \
    --corpus-dir "$CORPUS_DIR"
fi

echo
echo "[5/5] Building knowledge records, collections, and synthesis..."
POSTPROCESS_ARGS=(
  postprocess
  --corpus "$CORPUS_DIR"
  --taxonomy-profile "$TAXONOMY_PROFILE"
  --semantic-provider "$SEMANTIC_PROVIDER"
)
[[ -z "$SEMANTIC_MODEL" ]] || POSTPROCESS_ARGS+=(--model "$SEMANTIC_MODEL")
[[ -z "$SEMANTIC_BASE_URL" ]] || POSTPROCESS_ARGS+=(--base-url "$SEMANTIC_BASE_URL")
[[ "$FORCE_NORMALIZATION" != "1" ]] || POSTPROCESS_ARGS+=(--force-normalization)
[[ "$FORCE_ANALYSIS" != "1" ]] || POSTPROCESS_ARGS+=(--force-analysis)
python "$SCRIPT_DIR/06_build_knowledge.py" "${POSTPROCESS_ARGS[@]}"

echo
echo "============================================================"
echo "DONE"
echo "Final corpus:"
echo "$CORPUS_DIR/papers"
echo "============================================================"
