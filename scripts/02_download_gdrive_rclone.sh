#!/usr/bin/env bash
set -euo pipefail

DRIVE_INPUT="${1:-}"
OUT_DIR="${2:-}"
REMOTE="${3:-amity}"
REMOTE="${REMOTE%:}"

if [[ -z "$DRIVE_INPUT" || -z "$OUT_DIR" ]]; then
  echo "Usage:"
  echo "  bash scripts/02_download_gdrive_rclone.sh <google_drive_folder_link_or_id> <download_output_dir> [rclone_remote]"
  echo
  echo "Example:"
  echo "  bash scripts/02_download_gdrive_rclone.sh 'https://drive.google.com/drive/folders/XXXX' /tmp/downloaded amity"
  exit 1
fi

if ! command -v rclone >/dev/null 2>&1; then
  echo "ERROR: rclone not found. Install rclone and configure Google Drive remote first."
  exit 2
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "ERROR: jq not found. Install jq so Google Drive PDFs can be selected by MIME type."
  exit 2
fi

extract_id() {
  local s="$1"

  if [[ "$s" =~ folders/([A-Za-z0-9_-]+) ]]; then
    echo "${BASH_REMATCH[1]}"
    return
  fi

  if [[ "$s" =~ id=([A-Za-z0-9_-]+) ]]; then
    echo "${BASH_REMATCH[1]}"
    return
  fi

  echo "$s"
}

FOLDER_ID="$(extract_id "$DRIVE_INPUT")"

mkdir -p "$OUT_DIR"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

DRIVE_LIST_JSON="$TMP_DIR/drive_lsjson.json"
PDF_LIST_TSV="$TMP_DIR/pdf_paths.tsv"
LOG_FILE="$OUT_DIR/rclone_download.log"
: > "$LOG_FILE"

echo "Google Drive input: $DRIVE_INPUT"
echo "Folder ID: $FOLDER_ID"
echo "Remote: $REMOTE"
echo "Output: $OUT_DIR"
echo

rclone lsjson "${REMOTE}:" \
  --drive-root-folder-id "$FOLDER_ID" \
  --files-only \
  --recursive \
  > "$DRIVE_LIST_JSON"

jq -r '.[] | select(.MimeType == "application/pdf") | [.Path, .Size] | @tsv' \
  "$DRIVE_LIST_JSON" > "$PDF_LIST_TSV"

PDF_REMOTE_COUNT="$(wc -l < "$PDF_LIST_TSV" | tr -d ' ')"
echo "Remote PDFs found by MIME type: $PDF_REMOTE_COUNT"

if [[ "$PDF_REMOTE_COUNT" == "0" ]]; then
  echo "ERROR: no Google Drive files with MIME type application/pdf were found."
  exit 3
fi

while IFS=$'\t' read -r REMOTE_PATH REMOTE_SIZE; do
  TARGET_PATH="$OUT_DIR/$REMOTE_PATH"

  if [[ ! "$TARGET_PATH" =~ \.[Pp][Dd][Ff]$ ]]; then
    TARGET_PATH="$TARGET_PATH.pdf"
  fi

  mkdir -p "$(dirname "$TARGET_PATH")"

  echo
  echo "Downloading: $REMOTE_PATH"
  echo "Target: $TARGET_PATH"
  echo "Size: $REMOTE_SIZE bytes"

  rclone copyto "${REMOTE}:$REMOTE_PATH" "$TARGET_PATH" \
    --drive-root-folder-id "$FOLDER_ID" \
    --transfers 1 \
    --checkers 4 \
    --drive-chunk-size 64M \
    --retries 10 \
    --low-level-retries 20 \
    -P \
    --log-file "$LOG_FILE" \
    --log-level INFO
done < "$PDF_LIST_TSV"

MISSING_COUNT=0
while IFS=$'\t' read -r REMOTE_PATH _; do
  TARGET_PATH="$OUT_DIR/$REMOTE_PATH"

  if [[ ! "$TARGET_PATH" =~ \.[Pp][Dd][Ff]$ ]]; then
    TARGET_PATH="$TARGET_PATH.pdf"
  fi

  if [[ ! -s "$TARGET_PATH" ]]; then
    echo "WARNING: expected downloaded PDF missing or empty: $TARGET_PATH"
    MISSING_COUNT=$((MISSING_COUNT + 1))
  fi
done < "$PDF_LIST_TSV"

if [[ "$MISSING_COUNT" -gt 0 ]]; then
  echo "ERROR: $MISSING_COUNT expected PDF(s) were not downloaded correctly."
  exit 4
fi

echo
echo "Download complete."
echo "PDF count:"
find "$OUT_DIR" -type f \( -iname "*.pdf" -o -iname "*.PDF" \) | wc -l
