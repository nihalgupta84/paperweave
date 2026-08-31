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
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[full]"
```

`.[full]` installs the complete PDF workflow, including MinerU. For DOCX/HTML
and deterministic analysis only, use `python -m pip install -e .` instead.

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
    ├── collections/    ← generated multi-facet indexes
    └── synthesis/      ← five review-ready reports
```

Run it again after adding papers. Existing exact duplicates are not processed
again, and successful documents remain usable if another document fails.

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
normalized. Fuzzy title matches are flagged for review, never silently merged.

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
`--strict-provider` only when fallback should be an error.

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
paperweave --help
bash scripts/05_run_all.sh --help
bash scripts/99_status.sh /path/to/my_project/corpus
```

Stage controls are available when only part of a corpus needs work:
`--retry-failed`, `--force-mineru`, `--force-normalization`, and
`--force-analysis`.

## 📦 Installation choices

| Install | Best for |
| --- | --- |
| `python -m pip install -e .` | DOCX/HTML and deterministic CPU analysis |
| `python -m pip install -e ".[pdf]"` | PDF metadata helpers |
| `python -m pip install -e ".[full]"` | Complete PDF + MinerU workflow |
| `python -m pip install -e ".[dev]"` | Tests, builds, and release checks |

After the first PyPI release:

```bash
python -m pip install "paperweave[full]"
```

GPU acceleration is optional. No API key is needed for the default workflow.

## ⚖️ Scope and limitations

PaperWeave does not claim that an extracted fact is scientifically true; it
makes the source evidence inspectable. Review documents marked `review_needed`
in `quality.json`. Automatic fuzzy work merging, citation-graph enrichment,
vector retrieval, and figure-to-pipeline reconstruction are future extensions.

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
- [GROBID](https://github.com/kermitt2/grobid) as a planned optional scholarly
  metadata adapter; it is not required by the current pipeline.

Please follow each upstream project’s own license and citation guidance. See
[`CITATION.cff`](CITATION.cff) for citing PaperWeave.

## 👩‍💻 Development and release

```bash
python -m pip install -e ".[dev]"
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
