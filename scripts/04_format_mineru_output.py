#!/usr/bin/env python3
"""Compatibility wrapper for the installed MinerU normalizer."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from corpus_converter.mineru import main

if __name__ == "__main__":
    main()
