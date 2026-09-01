# Research Corpus Implementation Plan

## Objective

Build a reusable, evidence-backed research corpus from project-local scholarly
documents. The first useful system must solve the routine workflow before adding databases or
graph infrastructure:

```text
corpus/pdfs and corpus/sources/{docx,html}
  -> MinerU or native format adapter
  -> normalized papers
  -> structured records
  -> faceted collections
  -> corpus-level synthesis
```

The source of truth will be structured records with document provenance. Raw
MinerU output and generated Markdown are retained as inputs and views,
respectively; neither is the canonical knowledge representation.

## Implementation Status

The deterministic end-to-end MVP is implemented through Phase 5. It has been
verified with synthetic MinerU v2 fixtures and a real MinerU 3.4.0 legacy corpus.
Phase 6 metadata enrichment, local hybrid retrieval, and explainable corpus
graphs are implemented as optional or automatically generated extensions. The
complete pipeline is exposed through the installed `paperweave run` command;
repository shell scripts are no longer required for normal use.

## Open-Source Hardening Status

Implemented:

1. Per-document MinerU reconciliation and failure isolation.
2. PDF preflight with password-protected quarantine and parser warnings.
3. CPU/GPU capability reporting.
4. Ollama and OpenAI-compatible structured-output providers.
5. Transparent deterministic fallback with recorded reasons.
6. Gold-corpus evaluation command for user-verified labels.
7. Exact-title work grouping and fuzzy-match review candidates.
8. Per-document quality diagnostics.
9. Stage-specific force/retry controls for expensive stages.
10. MIT license, contribution/security guidance, and GitHub CI.
11. Synthetic tests spanning MinerU v2, PDF deduplication, DOCX, HTML,
    unsupported files, format preference, and unavailable-model fallback.
12. Native DOCX and HTML adapters producing the canonical block schema.
13. Package-native local and rclone/Google Drive orchestration from ingestion
    through reports, search indexes, and graphs.

Exact duplicates inside a corpus are quarantined recoverably before extraction.
Distinct PDF versions are retained as documents under one work; equivalent
lower-priority DOCX/HTML representations are retained but skipped by default.

## Canonical Workspace Layout

```text
corpus/
├── pdfs/                         # Selected source PDFs
├── sources/
│   ├── docx/                     # Selected DOCX sources
│   └── html/                     # Selected HTML sources
├── raw/
│   ├── mineru/                   # Untouched MinerU output
│   └── grobid/                   # Optional metadata output
├── papers/
│   └── <document_id>/
│       ├── paper.md
│       ├── blocks.jsonl
│       ├── document.json
│       ├── assets/
│       └── .done
├── records/
│   └── <work_id>/
│       ├── work.json
│       ├── analysis.json
│       ├── experiments.json
│       └── taxonomy.json
├── collections/
├── synthesis/
│   ├── methodology.md
│   ├── experiments.md
│   ├── datasets.md
│   ├── literature_review.md
│   ├── references.md
│   └── all_papers.md
├── manifests/
│   └── documents.jsonl
└── logs/
```

`raw_pdfs/`, `mineru_raw/`, and `extracted/` are legacy paths. During migration,
readers may support them, but new writes use `pdfs/`, `raw/mineru/`, and
`papers/`.

## Core Invariants

1. A document is one exact PDF and is identified by `doc_<sha256-prefix>`.
2. A work is a scholarly identity that may have multiple document versions.
3. Documents with the same normalized title share a work ID. Fuzzy title
   matches remain review candidates; automatic merging requires an exact DOI or
   arXiv match and preserves both original work directories in quarantine.
4. PDFs are never duplicated into taxonomy folders.
5. Raw parser output is never modified by normalization.
6. Every extracted claim or result must cite normalized evidence blocks.
7. Generated collections and reports can always be rebuilt from records.
8. Pipeline stages are resumable and skip completed inputs by default.

## Phase 1 — Stable Documents and MinerU Normalization

Status: implemented and verified.

Deliverables:

- Scan/copy supported documents into canonical source directories.
- Write `manifests/documents.jsonl` with hashes and stable IDs.
- Run MinerU into `corpus/raw/mineru`.
- Normalize each MinerU paper into one flat `papers/<document_id>/` directory.
- Produce `paper.md`, `document.json`, `blocks.jsonl`, and `assets/`.
- Report per-stage corpus status.

Acceptance criteria:

- N unique PDF hashes produce N manifest records.
- N successfully parsed selected documents produce N paper directories.
- No paper directory is nested inside another paper directory.
- Every block has a stable `block_id`, document ID, type, page index when
  available, text, bounding box when available, and source locator.
- Re-running without `--force` does not redo completed normalization.

## Phase 2 — Section Layer

Status: implemented and verified on real headings.

Add canonical section roles while retaining original headings:

```text
abstract, introduction, related_work, methodology, experiments, datasets,
results, discussion, limitations, conclusion, appendix, unknown
```

Acceptance criterion: manually verify section assignment on at least five
structurally different papers.

## Phase 3 — Evidence-Backed Semantic Records

Status: deterministic extractive implementation complete. Model enrichment is
deferred until evaluated on a gold corpus.

Define and validate small schemas for:

- research problem, method, contributions, components, and limitations;
- datasets, metrics, baselines, implementation details, results, and ablations;
- evidence references and support status.

Use targeted section passes through a replaceable structured-output LLM
provider. JSON-schema validity is necessary but insufficient: all block IDs,
pages, sections, and numerical evidence must be checked deterministically.

Support states:

```text
supported, partially_supported, ambiguous, unsupported, not_reported
```

## Phase 4 — Faceted Taxonomy and Collections

Status: core and optical-flow profiles implemented; collections are generated.

Use stable taxonomy IDs, aliases, and parent relationships for generic facets:

```text
task, condition, method_family, learning_paradigm, modality, research_goal,
paper_role, dataset, metric, application_domain
```

Domain packs, beginning with optical flow, extend the core taxonomy. Generate
collection Markdown by facet without copying PDFs.

## Phase 5 — Corpus Synthesis

Status: all six reports implemented and generated in the tested pipeline.

Generate six views from supported structured records:

- `methodology.md`: cross-paper method organization and comparison.
- `experiments.md`: protocols, baselines, metrics, results, and ablations.
- `datasets.md`: dataset-centric usage and evaluation view.
- `literature_review.md`: thematic evidence-backed synthesis and gaps.
- `references.md`: extracted bibliography entries with source-block provenance.
- `all_papers.md`: archival concatenation of normalized paper Markdown.

`all_papers.md` is not the default context for agents because large corpora can
exceed model context windows.

## Phase 6 — Evaluation and Metadata Enrichment

Create a stratified 10–20-paper gold corpus and measure metadata, taxonomy,
dataset/result extraction, evidence validity, and unsupported-claim rates.
Basic deterministic reference extraction and candidate citation linking are
implemented. The optional GROBID client now submits PDFs to
`processFulltextDocument`, preserves raw TEI, parses headers and references, and
fills only missing metadata. Conflicts remain explicit and provenance-aware.

## Phase 7 — Local Retrieval and Corpus Graphs

Status: implemented and tested.

- SQLite FTS5 exact-term retrieval with a fallback when FTS5 is unavailable.
- Deterministic hashed TF-IDF sparse vectors and hybrid rank fusion.
- Citation links with verified and candidate states.
- Related-paper links based on taxonomy, datasets, method text, and
  bibliographic coupling.
- Heterogeneous paper–dataset–taxonomy graph in JSON and GraphML.

These are corpus-local discovery tools. External citation expansion and neural
embeddings remain replaceable future backends.

## Phase 8 — Web Access and Connectors

Status: planned. See `docs/web_roadmap.md`.

The web application will consume the existing CLI/service layer rather than
creating a second pipeline. Local folders remain the default. Google Drive is
an explicit connector, and Cloudflare Tunnel is an optional route to a secured
operator-hosted instance—not a substitute for authentication or multi-user
isolation.

## Deferred Integrations

Add these only after the structured corpus is accurate:

- OpenAlex enrichment;
- Qdrant for larger hybrid retrieval workloads;
- Neo4j or GraphRAG for graph-specific research questions;
- VLM-based figure reconstruction.

The immediate scientific quality metric is the fraction of accepted claims and
numeric results correctly supported by their cited source evidence.
