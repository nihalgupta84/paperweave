#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$(dirname "$SCRIPT_DIR")"

# Activate the virtual environment created by the README, or run this script
# from an already activated environment.
if [[ -f .venv/bin/activate ]]; then
  source .venv/bin/activate
fi

bash scripts/05_run_all.sh \
  --input "https://drive.google.com/drive/folders/YOUR_FOLDER_ID?usp=sharing" \
  --corpus-dir /path/to/project/corpus \
  --device gpu \
  --rename-mode title \
  --format-policy prefer-pdf \
  --taxonomy-profile core
