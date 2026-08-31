#!/usr/bin/env bash
set -euo pipefail

EXTRAS="${1:-pdf}"
case "$EXTRAS" in
  minimal|pdf|full|dev) ;;
  *)
    echo "Usage: bash scripts/install.sh [minimal|pdf|full|dev]"
    exit 1
    ;;
esac

python -m pip install --upgrade pip
if [[ "$EXTRAS" == "minimal" ]]; then
  python -m pip install -e .
else
  python -m pip install -e ".[${EXTRAS}]"
fi

echo
echo "Installed PaperWeave ($EXTRAS). Try: paperweave --help"
