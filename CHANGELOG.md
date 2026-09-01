# Changelog

## [0.2.0] - 2026-09-01

- Preserve prior manifest records when ingesting one new file or a partial folder.
- Add DOI/arXiv-aware identity handling and recall-safe near-duplicate matching.
- Make merges recoverable and require strong identifiers for automatic merging.
- Enforce packaged JSON Schemas at runtime for documents, blocks, analysis,
  experiments, and taxonomy records.
- Preserve PDF author, year, DOI, and arXiv metadata through MinerU normalization.
- Mark model-generated facts as evidence-cited but semantically unverified.
- Add coordinate-aware evidence validation and candidate/verified citation edges.
- Add content-fingerprint synthesis invalidation and interactive duplicate review.
- Add six grounded reports, reference extraction, citation graphs, and structured exports.
- Expand regression coverage and enforce Ruff and formatting checks in CI.
- Add a functional optional GROBID TEI metadata/reference integration.
- Add local SQLite FTS5, sparse-vector, and hybrid block search.
- Add explainable related-paper links and heterogeneous JSON/GraphML knowledge graphs.

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
