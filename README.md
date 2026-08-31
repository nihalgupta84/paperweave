# PaperWeave

> Turn a messy folder of research files into an evidence-backed research workspace.

[![CI](https://github.com/nihalgupta84/paperweave/actions/workflows/ci.yml/badge.svg)](https://github.com/nihalgupta84/paperweave/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

PaperWeave is for the moment after you download papers and before you write a
literature review. It cleans and deduplicates the input, keeps PDF/DOCX/HTML
versions organized, extracts content, attaches evidence to structured facts,
and writes review-ready Markdown reports.

It works with a project-local `corpus/` directory. There is no global corpus to
configure and no required cloud LLM.

## Why use PaperWeave?

Research folders become difficult to trust for three common reasons:

- the same paper appears as a PDF, DOCX, HTML page, and renamed copy;
- one paper belongs to several useful topics, but a folder can express only one
  path;
- a language model can summarize a claim without showing exactly where it came
  from.

PaperWeave addresses all three in one repeatable workflow:

| Typical approach | What it leaves you to solve | PaperWeave’s answer |
| --- | --- | --- |
| PDF-to-Markdown conversion | duplicates, versions, and corpus organization | hash-based deduplication and work/document records |
| Topic folders | papers that belong to multiple topics | multi-facet collections without copying files |
| Embeddings-only RAG | exact evidence and reproducibility | block-level evidence, page data, and deterministic records |
| LLM-only summarization | unavailable models and unsupported claims | CPU-first extraction with optional, replaceable LLM enrichment |

PaperWeave is complementary to MinerU and retrieval systems: MinerU parses
complex PDF layout; PaperWeave turns parser output and native document formats
into a usable research corpus.

## 60-second start

From a checkout, install everything needed for the complete PDF workflow:

```bash
git clone https://github.com/nihalgupta84/paperweave.git
cd paperweave
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[full]"
```

Point the pipeline at one file or any mixed folder:

```bash
bash scripts/05_run_all.sh \
  --input /path/to/papers \
  --corpus-dir /path/to/my_project/corpus \
  --device auto
```

The default is intentionally simple: exact duplicates are removed before
extraction, PDF is preferred when the same work also has DOCX/HTML, and
deterministic analysis runs even when no local LLM is available.

For DOCX/HTML-only work, avoid the heavy PDF stack:

```bash
python -m pip install -e .
paperweave ingest --input /path/to/documents --corpus /path/to/my_project/corpus
paperweave normalize-non-pdf --corpus /path/to/my_project/corpus
paperweave postprocess --corpus /path/to/my_project/corpus
```

After a PyPI release, the equivalent installation will be:

```bash
python -m pip install "paperweave[full]"
```

## Your existing `corpus/` workflow

You can keep downloading into a project’s own corpus directory. A typical
layout is:

```text
my_project/
└── corpus/
    ├── incoming/       # optional staging area for rclone or manual downloads
    ├── pdfs/           # created and managed by PaperWeave
    ├── papers/         # clean per-document Markdown and blocks
    ├── records/        # evidence-backed structured records
    └── synthesis/      # the reports you read
```

Run the same command after adding more files:

```bash
bash scripts/05_run_all.sh \
  --input /path/to/my_project/corpus/incoming \
  --corpus-dir /path/to/my_project/corpus \
  --device auto
```

For Google Drive, the input may be a folder URL or folder ID. PaperWeave does
not assume a particular rclone remote: if exactly one remote is configured it
is selected automatically. If you have several remotes, pass yours explicitly:

```bash
bash scripts/05_run_all.sh \
  --input "https://drive.google.com/drive/folders/<folder-id>" \
  --corpus-dir /path/to/my_project/corpus \
  --remote <your-rclone-remote> \
  --device auto
```

The Google Drive helper requires [rclone](https://github.com/rclone/rclone)
and `jq`; local folders require neither.

## What happens to each input?

| Input | Behavior |
| --- | --- |
| One PDF, DOCX, HTML, or HTM | Process that document |
| Recursive mixed folder | Process every supported document and log unrelated files |
| Exact byte duplicate | Process once; quarantine an in-corpus duplicate recoverably |
| Same work as PDF + DOCX + HTML | Keep all records; process the preferred format by default (`PDF > DOCX > HTML`) |
| Different PDF versions | Keep them as distinct documents under a work record |
| CSV, PNG, JPEG, ZIP, or other unsupported file | Skip it and record the reason |
| Password-protected PDF | Move it to `quarantine/unreadable/` and continue |
| No GPU | Use CPU where supported; PDF parsing may be slower |
| No local LLM | Use deterministic extraction; provider failure is recorded, not hidden |

Use `--format-policy all` when you deliberately want every distinct
representation normalized. Fuzzy title matches are flagged for review and are
never silently merged.

## What you get

The most useful outputs are in `corpus/synthesis/`:

```text
methodology.md       # methods, components, and limitations
experiments.md       # datasets, metrics, baselines, and reported results
datasets.md          # dataset-centric view
literature_review.md # evidence-backed thematic index
all_papers.md        # combined normalized corpus Markdown
```

The supporting record for each work is stored under `corpus/records/`. Every
accepted fact points back to a normalized block, page, and section when the
source provides that information. `corpus/collections/` contains generated
facets such as method family, condition, dataset, and research goal; papers
are referenced, not copied into multiple folders.

## No-GPU and no-LLM operation

PaperWeave is useful without a model server. The default semantic stage is
deterministic and extractive. Ollama and OpenAI-compatible endpoints are
optional:

```bash
paperweave postprocess \
  --corpus /path/to/my_project/corpus \
  --semantic-provider ollama \
  --model <model-name>
```

If the endpoint is missing, the run falls back to deterministic analysis and
records the reason in `corpus/manifests/last_run.json`. Use
`--strict-provider` only when a missing model should fail the run.

## Useful commands

```bash
paperweave capabilities
bash scripts/99_status.sh /path/to/my_project/corpus
bash scripts/05_run_all.sh --help
```

To repair only a failed or changed stage, use `--retry-failed`,
`--force-mineru`, `--force-normalization`, or `--force-analysis`. Use
`--taxonomy-profile core` for a general corpus or
`--taxonomy-profile computer_vision/optical_flow` for the included example
profile.

## What makes this project different

PaperWeave is not a new foundation model or a replacement for MinerU. Its value
is the research workflow around extraction:

1. **Identity before extraction:** hashes, canonical names, work grouping, and
   format preference prevent duplicate processing.
2. **Evidence before prose:** structured facts retain source locations, so an
   agent can inspect evidence instead of treating a generated summary as truth.
3. **Facets instead of folders:** one paper can be low-light, Mamba-based,
   efficient, and evaluated on KITTI at the same time.
4. **Graceful degradation:** the useful deterministic path remains available
   on a CPU or when an LLM server is unavailable.
5. **Generated views:** reports, collections, and future retrieval indexes can
   be rebuilt from canonical records.

This makes PaperWeave useful to researchers who already have a paper folder and
want a clean, inspectable starting point for literature review, comparison,
gap analysis, and agent-assisted reading.

## Installation options

The package uses standard `pip` extras defined in `pyproject.toml`:

| Command | Use |
| --- | --- |
| `python -m pip install -e .` | DOCX/HTML and deterministic CPU workflow |
| `python -m pip install -e ".[pdf]"` | PDF metadata helpers |
| `python -m pip install -e ".[full]"` | Complete workflow, including MinerU |
| `python -m pip install -e ".[dev]"` | Build and development checks |

GPU acceleration is optional. `rclone` and `jq` are external command-line
tools used only for Google Drive ingestion. No API key is needed for the
default workflow.

## Project status and limitations

The current release is an early, deterministic corpus workflow. It does not
claim that extracted facts are scientifically true; it makes their source
evidence inspectable. Review low-quality documents reported in `quality.json`.
Automatic fuzzy work merging, citation-graph enrichment, vector retrieval,
and figure-to-pipeline reconstruction are intentionally separate extensions.

Downloaded papers and generated corpora may have redistribution restrictions.
Keep them out of Git unless their licenses permit redistribution. The
repository’s `.gitignore` is configured for this local-workspace model.

## Acknowledgements

PaperWeave is built around and interoperates with these open-source projects:

- [MinerU](https://github.com/opendatalab/MinerU) — PDF/document parsing and
  layout-aware Markdown/JSON extraction.
- [PyMuPDF](https://github.com/pymupdf/PyMuPDF) — PDF inspection and metadata
  support.
- [pypdf](https://github.com/py-pdf/pypdf) — lightweight PDF metadata and
  preflight support.
- [rclone](https://github.com/rclone/rclone) — optional Google Drive transfer.
- [Ollama](https://github.com/ollama/ollama) — optional local semantic provider.
- [vLLM](https://github.com/vllm-project/vllm) — compatible optional inference
  server for structured-output providers.
- [GROBID](https://github.com/kermitt2/grobid) — related scholarly metadata
  integration planned for a future optional adapter; it is not required by
  the current pipeline.

Please review each upstream project’s own license and citation guidance. See
[`CITATION.cff`](CITATION.cff) for citing PaperWeave itself.

## Development and release

```bash
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
python -m build
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md), [`SECURITY.md`](SECURITY.md), and
[`docs/releasing.md`](docs/releasing.md). Releases use PyPI Trusted Publishing
from GitHub Actions; no PyPI token belongs in this repo.

## License

PaperWeave is released under the [MIT License](LICENSE). This license applies
to PaperWeave code, not to papers processed by users or to upstream projects.
