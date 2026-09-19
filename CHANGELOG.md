# Changelog

## [0.4.3] - 2026-09-19

- **Autonomous Hardware-Aware Local LLM Execution**:
  - Automatically detect available VRAM across NVIDIA dedicated GPUs, enterprise container MIG slices, Apple Silicon unified memory (Metal), and CPU host memory with zero external dependencies.
  - Dynamically optimize model tier to safely maximize VRAM utilization without OOM crashes (e.g. 14B Q8 for 32GB+ A100, 14B Q6 for 16-24GB, 7B Q8 for 8-12GB, 3B for <7GB, and CPU throttling), backed by `llm-checker smart-recommend` when present.
  - Manage ephemeral background services: automatically start inactive local servers, pull missing models, and safely terminate child processes upon exit (`try...finally: resolution.cleanup()`) to prevent zombie processes and VRAM leaks.
  - Provide guaranteed zero-crash fallback to the 100% verified deterministic grounded engine if no local LLM runtime is available.
- **Dataset Extraction & Quality Audit Overhaul**:
  - Eliminate table header leaks (`TABLE II COMPARISON RESULTS ON THE TRANSCG` -> `TransCG`), unify sub-splits and naming variants via canonical maps, and add independent table/verb/question audit heuristics.
  - Integrate Dataset Density Audit (warning when unique datasets / scholarly works > 1.5).
  - Reduced spurious dataset mentions from 104 down to 31 genuine benchmarks across the 43-paper corpus.
- **CLI & Workflow Enhancements**:
  - Add `--force` flag to `paperweave analyze` for fast re-analysis without re-running OCR.
  - Add `auto-local` alias to `--semantic-provider` and enhance `capabilities` output with detailed VRAM budget and recommended model tier.

## [0.4.2] - 2026-09-18

- Intelligently discover and prioritize compatible MinerU 3.x installations from dedicated conda environments (`/workspace/miniconda3/envs/mineru`, `~/miniconda3/envs/mineru`, etc.) and prevent conflicts with incompatible MinerU 4.x CLI.
- Add `--mineru-path` CLI option and `MINERU_PATH` / `MINERU_BIN` environment variables for explicit executable selection.
- Isolate subprocess environment PATH to the detected MinerU executable directory to avoid cross-environment library shadowing.
- Handle containerized GPU detection when `nvidia-smi` reports `[Insufficient Permissions]` for memory attributes.

## [0.4.1] - 2026-09-18

- Streamline `README.md` with interactive collapsible `<details>` dropdowns and dedicated setup guides for Google Drive rclone (`docs/setup_rclone.md`) and local Ollama (`docs/setup_ollama.md`).
- Clarify evidence coordinate extraction with explicit framing of rectal cancer as an illustrative project corpus.
- Apply `ruff format` across codebase and test suite to ensure 100% clean CI checks.

## [0.4.0] - 2026-09-18

- Add automated quality self-audit report (`synthesis/quality_report.md`) auditing
  evidence coordinates, dataset hygiene, grouping consistency, and metric extraction.
- Implement intelligent preprint and published journal auto-merging with Union-Find
  clustering, subtitle stripping, Unicode author surname matching, and preprint DOI
  recognition (allowing arXiv/bioRxiv/Research Square and journal versions to unify).
- Prevent dataset false positives with expanded stopwords, section-title prefix
  rejection, sentence-boundary guards, and spaced-acronym normalization.
- Expand cross-domain metric taxonomy with 40+ benchmarks across Computer Vision,
  NLP, Medical Imaging, Speech, and Generative Modeling, backed by strict token regex
  and non-metric blocklists.
- Deduplicate dataset benchmark synthesis by normalized name and add corpus-level
  summary statistics to the navigation README.
- Deduplicate work aggregate records in ingestion manifest to prevent duplicate entries.

## [0.3.0] - 2026-09-02

- Replace the verbose run result with a concise human summary; retain full
  parser output in logs and expose it through `--verbose` or `--json`.
- Accept `paperweave run <path>` and infer a safe corpus destination, rejecting
  output nested inside input and ignoring nested generated corpora.
- Discover named datasets from evidence text instead of relying only on a fixed
  vocabulary; use token-boundary matching to prevent false metric mentions.
- Create a compact text corpus by default and remove newly generated MinerU
  intermediates after successful normalization; visual assets are opt-in.
- Add `paperweave compact` for existing corpora and write a navigation README
  into every generated corpus.
- Add optional automatic local-model selection using llm-checker's ranking of
  already-installed Ollama models, with deterministic fallback.
- Rewrite public documentation without project-specific paths and add focused
  output and graph guides.

## [0.2.2] - 2026-09-01

- Remove a harmless unused workflow variable that failed clean CI linting.
- Disable Ruff's cache in pre-commit hooks so auto-fix follow-up issues cannot
  be hidden by a cached second run.

## [0.2.1] - 2026-09-01

- Add `paperweave run` as a package-native end-to-end workflow, so PyPI users
  no longer depend on repository shell scripts.
- Move MinerU normalization into the installed Python package while retaining a
  compatibility wrapper for cloned repositories.
- Add package-native Google Drive ingestion through rclone.
- Replace MinerU's very broad `all` extra with the focused `pipeline` backend
  required by PaperWeave's default PDF workflow.
- Explain base versus PDF/full installations and provide actionable missing-
  MinerU and executable-path errors.
- Rewrite the README around separate PyPI-user and source-development paths.

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
