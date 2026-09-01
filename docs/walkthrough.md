# PaperWeave Walkthrough

## Current Goal

Convert project-local research documents into a clean, reusable corpus that supports
evidence-backed literature analysis without nested output folders or duplicated
PDF category trees.

## Current Phase

Backend v0.2.1 release candidate implemented and verified, including multi-format
ingestion, GROBID enrichment, local hybrid retrieval, corpus graphs, model
fallback, failure isolation, and an installed-package `paperweave run` workflow.
Web access is planned separately.

## Pipeline

```text
PDF/DOCX/HTML -> dedup/work selection -> parser adapter -> normalized papers -> sections -> records
     -> taxonomy -> collections -> six core reports + search index + paper/knowledge graphs
```

PyPI users run this pipeline with `paperweave run --input ... --corpus ...`.
Repository shell scripts are compatibility/development tools, not a requirement
for installed-package use.

The trusted extraction layer is deterministic and extractive. Rich model-authored
narrative synthesis remains optional rather than being mixed into source records.

## Key Decisions

- `corpus/pdfs` is the canonical input path.
- `corpus/raw/mineru` preserves parser output.
- `corpus/papers/<document_id>` is the clean document store.
- SHA-256-derived document IDs are stable across title corrections.
- Exact normalized-title matches share a work ID; fuzzy matches remain explicit
  review candidates. Automatic merging additionally requires an exact DOI or
  arXiv match and retains recoverable pre-merge snapshots.
- Taxonomy folders will be generated views, not physical PDF organization.
- The graph distinguishes verified citations, fuzzy-title candidates, computed
  related-paper links, and dataset/taxonomy knowledge edges.
- Local search combines SQLite FTS5 and hashed TF-IDF vectors without requiring
  a model or GPU. Neural embeddings remain an optional future backend.
- GROBID is optional and fills missing metadata without hiding conflicts.

## Immediate Acceptance Test

Completed on synthetic MinerU v2 fixtures and a real legacy MinerU 3.4.0 corpus.
The real run normalized 12 papers and 2,782 blocks, validated 746 evidence
references with zero invalid references, generated 19 collections, and wrote all
six synthesis reports.

The v0.2 backend was additionally rerun on two retained real medical-imaging
PDFs and their MinerU 3.4.0 artifacts. It normalized 491 blocks and 99 assets,
validated 68/68 evidence locators, generated nine collections and all six core
reports, indexed 421 searchable text blocks with FTS5 enabled, returned grounded
hybrid-search results, and produced one related-paper link plus an 11-node,
15-edge heterogeneous knowledge graph. No live GROBID server was installed; the
optional probe returned a non-fatal unavailable result as designed, while the
HTTP client and TEI parsing are covered by a local integration server test.

A fresh end-to-end MinerU 3.4.0 GPU extraction was then run for v0.2 on an
11-page rectal-cancer segmentation paper (rather than reusing retained parser
artifacts). Ingestion, extraction, reconciliation, normalization, and
postprocessing all completed without failed or review-needed documents. The run
produced 163 blocks and 12 assets, validated 26/26 evidence locators, generated
five collections and all six core reports, indexed 147 searchable blocks with
FTS5, returned relevant hybrid-search results, and generated the paper and
heterogeneous knowledge graphs.

For v0.2.1, the built wheel was installed into a clean Python 3.10 environment
and `paperweave run` completed an HTML corpus through normalization, evidence
validation, all reports, search, and graph generation without access to the
source repository. The same command was then run against the retained real PDF
corpus in the MinerU environment: it correctly detected the completed MinerU
output, skipped expensive re-extraction, retained 163 normalized blocks, and
completed postprocessing with zero invalid evidence locators. Python 3.10 also
successfully resolves the focused `paperweave[full]` MinerU pipeline extra.

## Next Steps

1. Review taxonomy aliases and extracted reports for the target research domain.
2. Evaluate the optional structured-output enrichment against a manually
   annotated gold corpus before relying on inferred claims in a paper.
3. Implement the local-first web milestone in `docs/web_roadmap.md`.
