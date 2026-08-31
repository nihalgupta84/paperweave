#!/usr/bin/env python3
"""Discover, deduplicate, identify, rename, and stage scholarly documents."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from corpus_converter.ingestion import ingest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="A PDF/DOCX/HTML file or recursive mixed folder.")
    parser.add_argument("--corpus-dir", required=True, help="Target corpus workspace.")
    parser.add_argument("--rename-mode", choices=["title", "keep"], default="title")
    parser.add_argument("--format-policy", choices=["prefer-pdf", "all"], default="prefer-pdf")
    parser.add_argument(
        "--keep-duplicates-in-place",
        action="store_true",
        help="Record exact duplicates but do not quarantine duplicates already inside the corpus.",
    )
    parser.add_argument("--force", action="store_true", help="Accepted for backward compatibility.")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    corpus = Path(args.corpus_dir).expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"Input path does not exist: {input_path}")
    result = ingest(
        input_path,
        corpus,
        rename_mode=args.rename_mode,
        format_policy=args.format_policy,
        quarantine_duplicates=not args.keep_duplicates_in_place,
    )
    print(json.dumps(result, indent=2))
    if not result["documents"]:
        raise SystemExit("No supported PDF, DOCX, HTML, or HTM documents found.")


if __name__ == "__main__":
    main()
