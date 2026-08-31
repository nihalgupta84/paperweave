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
  echo "ERROR: jq not found. Install jq so supported Google Drive documents can be selected by MIME type."
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
FILE_LIST_TSV="$TMP_DIR/document_paths.tsv"
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

jq -r '.[] | select(
    .MimeType == "application/pdf" or
    .MimeType == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" or
    .MimeType == "text/html"
  ) | [.Path, .Size, .MimeType] | @tsv' "$DRIVE_LIST_JSON" > "$FILE_LIST_TSV"

DOCUMENT_REMOTE_COUNT="$(wc -l < "$FILE_LIST_TSV" | tr -d ' ')"
echo "Remote PDF/DOCX/HTML documents found by MIME type: $DOCUMENT_REMOTE_COUNT"

if [[ "$DOCUMENT_REMOTE_COUNT" == "0" ]]; then
  echo "ERROR: no supported PDF, DOCX, or HTML documents were found."
  exit 3
fi

while IFS=$'\t' read -r REMOTE_PATH REMOTE_SIZE MIME_TYPE; do
  TARGET_PATH="$OUT_DIR/$REMOTE_PATH"

  case "$MIME_TYPE" in
    application/pdf) [[ "$TARGET_PATH" =~ \.[Pp][Dd][Ff]$ ]] || TARGET_PATH="$TARGET_PATH.pdf" ;;
    application/vnd.openxmlformats-officedocument.wordprocessingml.document) [[ "$TARGET_PATH" =~ \.[Dd][Oo][Cc][Xx]$ ]] || TARGET_PATH="$TARGET_PATH.docx" ;;
    text/html) [[ "$TARGET_PATH" =~ \.[Hh][Tt][Mm][Ll]?$ ]] || TARGET_PATH="$TARGET_PATH.html" ;;
  esac

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
done < "$FILE_LIST_TSV"

MISSING_COUNT=0
while IFS=$'\t' read -r REMOTE_PATH _ MIME_TYPE; do
  TARGET_PATH="$OUT_DIR/$REMOTE_PATH"

  case "$MIME_TYPE" in
    application/pdf) [[ "$TARGET_PATH" =~ \.[Pp][Dd][Ff]$ ]] || TARGET_PATH="$TARGET_PATH.pdf" ;;
    application/vnd.openxmlformats-officedocument.wordprocessingml.document) [[ "$TARGET_PATH" =~ \.[Dd][Oo][Cc][Xx]$ ]] || TARGET_PATH="$TARGET_PATH.docx" ;;
    text/html) [[ "$TARGET_PATH" =~ \.[Hh][Tt][Mm][Ll]?$ ]] || TARGET_PATH="$TARGET_PATH.html" ;;
  esac

  if [[ ! -s "$TARGET_PATH" ]]; then
    echo "WARNING: expected downloaded document missing or empty: $TARGET_PATH"
    MISSING_COUNT=$((MISSING_COUNT + 1))
  fi
done < "$FILE_LIST_TSV"

if [[ "$MISSING_COUNT" -gt 0 ]]; then
  echo "ERROR: $MISSING_COUNT expected PDF(s) were not downloaded correctly."
  exit 4
fi

echo
echo "Download complete."
echo "Supported document count:"
find "$OUT_DIR" -type f \( -iname "*.pdf" -o -iname "*.docx" -o -iname "*.html" -o -iname "*.htm" \) | wc -l
