# 📚 PaperWeave

> **From a messy paper folder to a review-ready research workspace.**

[![CI](https://github.com/nihalgupta84/paperweave/actions/workflows/ci.yml/badge.svg)](https://github.com/nihalgupta84/paperweave/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/paperweave?color=3776AB&label=PyPI)](https://pypi.org/project/paperweave/)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-2EA44F)](LICENSE)

PaperWeave is a small, evidence-first pipeline for researchers who already
have papers and want to understand them systematically. Give it one file or a
folder; it deduplicates, organizes, extracts, and creates grounded Markdown
reports for literature review.

> [!TIP]
> **If you remember only one command:**
> `bash scripts/05_run_all.sh --input /path/to/papers --corpus-dir /path/to/project/corpus`

## ✨ Why PaperWeave?

Paper folders usually fail in three places:

1. the same work appears as a PDF, DOCX, HTML page, and renamed copy;
2. one paper belongs to several topics, but a single folder path cannot express
   that;
3. a generated summary says *what* a paper claims but not *where* the claim
   came from.

PaperWeave solves these together:

| Instead of… | You get… |
| --- | --- |
| processing every copy | SHA-256 deduplication before extraction |
| making one deep folder tree | multi-facet collections: method, condition, dataset, goal |
| trusting a free-form summary | structured facts linked to blocks, pages, and sections |
| depending on one model server | deterministic CPU output with optional LLM enrichment |

It is not another foundation model, PDF viewer, or embeddings-only chatbot.
It is the reliable layer between downloaded documents and literature analysis.

## 🚀 Start in three steps

### 1. Install

```bash
git clone https://github.com/nihalgupta84/paperweave.git
cd paperweave
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -e ".[full]"
```

`.[full]` installs the complete PDF workflow, including MinerU. For DOCX/HTML
and deterministic analysis only, use `uv pip install -e .` instead. Install
[`uv`](https://docs.astral.sh/uv/getting-started/installation/) first if the
command is not already available.

### 2. Run

```bash
bash scripts/05_run_all.sh \
  --input /path/to/papers \
  --corpus-dir /path/to/my_project/corpus \
  --device auto
```

`--input` can be a single PDF/DOCX/HTML file or a recursive mixed folder.

### 3. Read the results

Open these files:

```text
/path/to/my_project/corpus/synthesis/
├── methodology.md
├── experiments.md
├── datasets.md
├── literature_review.md
├── references.md
└── all_papers.md
```

## 🗂️ Fits your existing project layout

You do not need a global corpus. Keep each project self-contained:

```text
my_project/
└── corpus/
    ├── incoming/       ← your rclone/manual download area
    ├── pdfs/           ← selected canonical PDFs
    ├── sources/        ← selected DOCX/HTML sources
    ├── papers/         ← clean Markdown, blocks, and assets
    ├── records/        ← work/document facts with evidence
    ├── indexes/        ← local SQLite lexical/vector search
    ├── collections/    ← generated multi-facet indexes
    └── synthesis/      ← review-ready reports and paper graph
```

Run it again after adding papers—even with a path to one new file. Existing
manifest records are preserved, exact duplicates are not processed again, and
successful documents remain usable if another document fails.

## 🧩 What happens to your files?

| Input | PaperWeave behavior |
| --- | --- |
| One PDF, DOCX, HTML, or HTM | Process that document |
| Folder with mixed files | Recursively process supported files; log the rest |
| Exact duplicate bytes | Process once; quarantine the extra copy recoverably |
| PDF + DOCX + HTML of one work | Keep all records; prefer PDF by default (`PDF > DOCX > HTML`) |
| Different PDF versions | Keep them as separate documents under one work |
| CSV, PNG, JPEG, ZIP, or other unsupported file | Skip and record the reason |
| Password-protected PDF | Move to `quarantine/unreadable/` and continue |
| No GPU | Use CPU where supported; PDF parsing may be slower |
| No local LLM | Use deterministic extraction and record the fallback |

Use `--format-policy all` when you want every distinct representation
normalized. Fuzzy title matches are flagged for review. Automatic merging is
allowed only when both the title threshold and an exact DOI or arXiv identifier
agree; every merge retains snapshots under `quarantine/merged_works/`.

## ☁️ Google Drive (optional)

Local folders need no cloud setup. For Drive, pass a folder URL or ID:

```bash
bash scripts/05_run_all.sh \
  --input "https://drive.google.com/drive/folders/<folder-id>" \
  --corpus-dir /path/to/my_project/corpus \
  --device auto
```

If exactly one rclone remote is configured, PaperWeave selects it automatically.
If you have several, add `--remote <your-rclone-remote>`. The helper uses
[rclone](https://github.com/rclone/rclone) and `jq`;

## 🧠 Optional local intelligence

No model server is required. The default analyzer is deterministic and
extractive. If you have Ollama or an OpenAI-compatible endpoint, add enrichment:

```bash
paperweave postprocess \
  --corpus /path/to/my_project/corpus \
  --semantic-provider ollama \
  --model <model-name>
```

If the provider is unavailable, the pipeline falls back to deterministic output
and records the reason in `corpus/manifests/last_run.json`. Use
`--strict-provider` only when fallback should be an error. Model-generated items
with valid block IDs are marked `evidence_cited_unverified`: a valid citation
proves traceability, not that the cited text semantically entails the claim.

GROBID can optionally improve scholarly metadata and bibliography extraction:

```bash
paperweave grobid \
  --corpus /path/to/my_project/corpus \
  --base-url http://127.0.0.1:8070
```

Conflicting GROBID values never silently replace canonical metadata. Raw TEI,
parsed metadata, and conflicts are retained under `corpus/raw/grobid/`. Add
`--grobid-url` to the one-command script to run this stage automatically.

## 🔎 Local search and paper maps

Postprocessing automatically builds a CPU-only SQLite index and corpus graph.
Search exact terms and related passages without an API key:

```bash
paperweave search --corpus /path/to/project/corpus "low-light optical flow"
paperweave search --corpus /path/to/project/corpus "KITTI EPE" --mode lexical
paperweave search --corpus /path/to/project/corpus "efficient flow" --mode vector
```

The default hybrid ranking fuses SQLite FTS5 with a deterministic hashed TF-IDF
vector. This is lightweight and reproducible, but it is not a neural semantic
embedding model. Larger future deployments can replace it with Qdrant or another
embedding backend.

When at least two papers are available, PaperWeave creates:

- directed in-corpus citation links, separated into identifier-verified and
  fuzzy-title candidate edges;
- explainable related-paper links using taxonomy, datasets, methodology text,
  and shared references;
- a heterogeneous knowledge graph connecting papers to datasets and taxonomy
  entities;
- JSON and GraphML exports for custom interfaces, NetworkX, Gephi, or Cytoscape.

```bash
paperweave graph --corpus /path/to/project/corpus
```

This provides corpus-local discovery inspired by the workflow of paper-mapping
tools; it does not query, clone, or claim parity with Connected Papers or Litmaps.

## 🔍 Why it is different

- **Identity before extraction** — hashes, canonical names, work grouping, and
  format preference prevent duplicate processing.
- **Evidence before prose** — every accepted fact can point back to its source
  block, page, and section.
- **Facets instead of folders** — a paper can be “low-light”, “Mamba”,
  “efficient”, and “KITTI” simultaneously.
- **Graceful degradation** — CPU and no-LLM workflows remain useful.
- **Rebuildable views** — reports and collections are generated from records,
  not hand-edited folder copies.

That is why someone should use PaperWeave: it turns an existing collection of
papers into an inspectable starting point for comparison, literature review,
gap analysis, and agent-assisted reading with minimal code.

## 🛠️ Useful commands

```bash
paperweave capabilities
paperweave --version
paperweave --help
paperweave review --corpus /path/to/project/corpus --interactive
paperweave graph --corpus /path/to/project/corpus
paperweave index --corpus /path/to/project/corpus
paperweave search --corpus /path/to/project/corpus "query"
paperweave grobid --corpus /path/to/project/corpus
paperweave export --corpus /path/to/project/corpus --format bibtex --output corpus.bib
bash scripts/05_run_all.sh --help
bash scripts/99_status.sh /path/to/my_project/corpus
```

Stage controls are available when only part of a corpus needs work:
`--retry-failed`, `--force-mineru`, `--force-normalization`, and
`--force-analysis`.

## 📦 Installation choices

| Install | Best for |
| --- | --- |
| `uv pip install -e .` | DOCX/HTML and schema-validated deterministic CPU analysis |
| `uv pip install -e ".[pdf]"` | PDF metadata helpers |
| `uv pip install -e ".[full]"` | Complete PDF + MinerU workflow |
| `uv pip install -e ".[dev]"` | Tests, builds, and release checks |

From PyPI:

```bash
uv pip install "paperweave[full]"
```

GPU acceleration is optional. No API key is needed for the default workflow.

## ⚖️ Scope and limitations

PaperWeave does not claim that an extracted fact is scientifically true; it
makes the source evidence inspectable. Review documents marked `review_needed`
in `quality.json`. Citation edges based only on fuzzy titles are marked
`candidate`; identifier-confirmed edges are marked `verified`. Related-paper
scores are discovery aids, not citation evidence. The built-in sparse vector
index is lexical rather than neural-semantic. Figure-to-pipeline reconstruction,
hosted multi-user service, and large-scale external citation discovery remain
future extensions.

Do not commit downloaded papers or generated corpora unless their licenses allow
redistribution. The repository’s `.gitignore` is designed for project-local
private corpora.

## 🙏 Acknowledgements

PaperWeave uses or interoperates with:

- [MinerU](https://github.com/opendatalab/MinerU) for layout-aware document
  parsing and Markdown/JSON extraction.
- [rclone](https://github.com/rclone/rclone) for optional Google Drive transfer.
- [Ollama](https://github.com/ollama/ollama) for optional local model serving.
- [vLLM](https://github.com/vllm-project/vllm) for compatible optional inference
  endpoints.
- [GROBID](https://github.com/kermitt2/grobid) through an optional scholarly
  metadata and bibliography adapter; it is not required by the core pipeline.

Please follow each upstream project’s own license and citation guidance. See
[`CITATION.cff`](CITATION.cff) for citing PaperWeave.

## 👩‍💻 Development and release

```bash
uv pip install -e ".[dev]"
python -m ruff check .
python -m ruff format --check .
python -m unittest discover -s tests -v
python -m build
python -m twine check dist/*
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md), [`SECURITY.md`](SECURITY.md), and
[`docs/releasing.md`](docs/releasing.md). PyPI uploads use GitHub Actions
Trusted Publishing; no API token belongs in the repository.

## 📄 License

PaperWeave is released under the [MIT License](LICENSE). This applies to
PaperWeave code, not to processed papers or upstream projects.
