#!/usr/bin/env python3
"""Build section, record, taxonomy, collection, and synthesis outputs."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from corpus_converter.cli import main


if __name__ == "__main__":
    main()
