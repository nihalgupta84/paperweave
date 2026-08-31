# Changelog

## [0.1.0] - 2026-08-31

First public release of PaperWeave.

- Ingest PDF, DOCX, HTML, and HTM files from one path or a recursive mixed folder.
- Deduplicate exact bytes before extraction and quarantine duplicates recoverably.
- Group equivalent titles into work records while retaining document versions.
- Prefer PDF, then DOCX, then HTML by default, with an `all` policy available.
- Normalize MinerU output and native DOCX/HTML into flat, provenance-linked documents.
- Generate methodology, experiments, datasets, literature-review, and combined reports.
- Provide deterministic CPU analysis plus optional Ollama/OpenAI-compatible enrichment.
- Add quality diagnostics, failure isolation, taxonomy collections, CI, and PyPI packaging.
