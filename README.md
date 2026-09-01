# 📚 PaperWeave

> Turn a folder of research papers into a deduplicated, searchable corpus with evidence-linked literature-review reports.

[![CI](https://github.com/nihalgupta84/paperweave/actions/workflows/ci.yml/badge.svg)](https://github.com/nihalgupta84/paperweave/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/paperweave?color=3776AB&label=PyPI)](https://pypi.org/project/paperweave/)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-2EA44F)](LICENSE)

PaperWeave accepts one paper or a folder containing PDF, DOCX, HTML, and HTM
documents. It removes exact duplicates before extraction, groups different file
versions of the same work, normalizes their content, and generates corpus-level
Markdown reports about methods, experiments, datasets, references, and the full
paper collection.

The default analysis is deterministic and runs without an LLM or API key.

## 🚀 Install and run from PyPI

This is the normal installation path. You do not need to clone the repository.

### For PDF, DOCX, and HTML

PDF extraction requires MinerU, which is included in the `full` installation:

```bash
python -m pip install --upgrade "paperweave[full]"
```

Then, from your research project:

```bash
paperweave run \
  --input paper_v2 \
  --corpus corpus \
  --device auto
```

For your underwater project, run that command from:

```text
~/nihal/underwater/uw_edge
```

It reads papers recursively from `paper_v2` and creates `uw_edge/corpus`.

### For DOCX and HTML only

The smaller base package does not install MinerU:

```bash
python -m pip install --upgrade paperweave
paperweave run --input /path/to/documents --corpus corpus
```

### Confirm the installation

```bash
paperweave --version
paperweave run --help
```

Installing PaperWeave does not create a `scripts/` folder in your project. The
installed interface is the `paperweave` command. A command such as
`bash scripts/05_run_all.sh` is available only inside a cloned PaperWeave source
repository.

## 🧑‍💻 Install from a cloned repository

Use this path when developing PaperWeave or changing its source code:

```bash
git clone https://github.com/nihalgupta84/paperweave.git
cd paperweave
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -e ".[full,dev]"
```

The recommended command remains the same:

```bash
paperweave run --input /path/to/papers --corpus /path/to/project/corpus
```

Repository shell scripts remain available for development and compatibility,
but they are not required by the installed package.

## 📥 Supported input

| Input | Behavior |
| --- | --- |
| One PDF, DOCX, HTML, or HTM file | Processes that document |
| A directory | Searches recursively for supported documents |
| PDF + DOCX + HTML of one work | Keeps every representation; selects PDF by default |
| Exact duplicate files | Processes one copy and records/quarantines the duplicate |
| Different versions of a paper | Keeps separate documents under one scholarly work |
| CSV, PNG, JPEG, ZIP, LaTeX, and other files | Skips them and records the reason |
| Password-protected or unreadable PDF | Isolates the failure and continues the batch |

Use `--format-policy all` to extract every distinct PDF/DOCX/HTML
representation instead of selecting `PDF > DOCX > HTML`.

PaperWeave does not treat image, CSV, or LaTeX files inside a project directory
as research papers. In a directory such as `paper_v2`, it will find `main.pdf`
and skip figures, tables, logs, YAML files, and source code.

## 📤 Generated corpus

```text
corpus/
├── pdfs/                    selected canonical PDFs
├── sources/                 selected DOCX/HTML files
├── raw/mineru/              untouched MinerU output
├── raw/grobid/              optional GROBID output
├── papers/<document_id>/    clean Markdown, blocks, and local assets
├── records/<work_id>/       structured facts and evidence
├── indexes/                 local search index
├── collections/             generated method/dataset/topic views
├── synthesis/               literature-review reports and graph summaries
├── manifests/               identities, stages, and run state
└── quarantine/              recoverable duplicates and failed inputs
```

The main reports are:

```text
corpus/synthesis/
├── methodology.md
├── experiments.md
├── datasets.md
├── literature_review.md
├── references.md
└── all_papers.md
```

Run the same command after adding papers. Existing successful documents are
preserved, and already completed extraction stages are skipped unless `--force`
is supplied.

## 🧠 GPU and LLM requirements

An LLM is not required. The default semantic provider is `deterministic` and
produces evidence-linked extractive records and reports.

| Situation | Result |
| --- | --- |
| No local LLM | The complete deterministic analysis still runs |
| No GPU | MinerU can use CPU, but PDF extraction will be slower |
| DOCX/HTML-only corpus | No MinerU or GPU is needed |
| Ollama/OpenAI-compatible model available | Optional schema-constrained enrichment can be enabled |

Force CPU parsing with:

```bash
paperweave run --input papers --corpus corpus --device cpu
```

Optional local-model enrichment:

```bash
paperweave run \
  --input papers \
  --corpus corpus \
  --semantic-provider ollama \
  --model qwen2.5:7b
```

If the optional provider is unavailable, PaperWeave records the reason and uses
deterministic extraction. Add `--strict-provider` only when fallback should be
an error.

## ☁️ Google Drive input

Configure an rclone Google Drive remote, then pass a folder URL or ID:

```bash
paperweave run \
  --input "https://drive.google.com/drive/folders/<folder-id>" \
  --corpus corpus \
  --remote mydrive
```

If exactly one rclone remote is configured, `--remote` can be omitted. Drive
support requires the external `rclone` command; it does not require cloning the
PaperWeave repository.

## 🔎 Search and paper graphs

The complete run builds a local SQLite search index and corpus knowledge graph.

```bash
paperweave search --corpus corpus "underwater enhancement UIEB"
paperweave graph --corpus corpus
```

With multiple papers, graph outputs distinguish:

- identifier-verified citations;
- fuzzy-title citation candidates;
- explainable related-paper links based on methods, datasets, taxonomy, and
  shared references;
- paper-to-dataset and paper-to-taxonomy knowledge edges.

These are corpus-local discovery tools. PaperWeave does not query the global
literature graph provided by services such as Connected Papers or Litmaps.

## 🧰 Command reference

| Command | Purpose |
| --- | --- |
| `paperweave run` | Complete documents-to-reports workflow |
| `paperweave review` | Inspect quality warnings and possible duplicates |
| `paperweave search` | Search normalized paper blocks |
| `paperweave graph` | Rebuild paper and knowledge graphs |
| `paperweave export` | Export BibTeX, CSV, or JSON-LD |
| `paperweave grobid` | Run optional GROBID metadata enrichment |
| `paperweave capabilities` | Show detected compute/model capabilities |

Every stage is also available separately through `paperweave --help` for users
who need manual control.

## ❓ Troubleshooting

### `scripts/05_run_all.sh: No such file or directory`

You installed PaperWeave from PyPI. Use the installed command:

```bash
paperweave run --input paper_v2 --corpus corpus
```

### `PDF extraction requires MinerU`

The base package was installed, but the input contains a selected PDF. Install
the complete PDF dependencies in the same Python environment:

```bash
python -m pip install --upgrade "paperweave[full]"
```

### `paperweave: command not found`

Confirm that installation and execution use the same interpreter:

```bash
python -m pip show paperweave
python -m site --user-base
```

For a `--user` installation, the executable is commonly under
`~/.local/bin`. Add that directory to `PATH`, or install inside an activated
virtual/Conda environment without `--user`.

### Existing Conda environment

Inside an activated environment, prefer:

```bash
python -m pip install --upgrade "paperweave[full]"
```

Using `--user` inside an environment can place the package and executable in a
different user-level location than expected.

## 🔬 Why PaperWeave is different

Reference managers organize citations. PDF parsers convert files. Chat-with-PDF
tools answer questions. PaperWeave connects these stages into a reusable local
corpus:

- identity and duplicate handling happen before expensive extraction;
- one paper can belong to multiple method, condition, dataset, and goal facets;
- extracted statements retain document, block, section, page, and coordinate
  provenance when available;
- deterministic output remains usable without a model server;
- reports, collections, search indexes, and graphs can be rebuilt from canonical
  records.

PaperWeave supports exploratory and narrative literature review workflows. It
is not currently a complete PRISMA protocol-management or global scholarly
discovery platform.

## ⚖️ Scientific and copyright boundaries

Evidence provenance makes a statement inspectable; it does not prove that the
paper's claim is scientifically correct. Model-enriched statements are marked
as evidence-cited but semantically unverified unless separately reviewed.

Do not redistribute downloaded papers, extracted figures, or full Markdown
unless their licenses allow it. Project corpora are ignored by the repository's
default Git rules.

## 🙏 Acknowledgements

PaperWeave uses or interoperates with:

- [MinerU](https://github.com/opendatalab/MinerU) for layout-aware PDF parsing;
- [GROBID](https://github.com/kermitt2/grobid) for optional scholarly metadata
  and bibliography extraction;
- [rclone](https://github.com/rclone/rclone) for optional Google Drive transfer;
- [Ollama](https://github.com/ollama/ollama) and
  [vLLM](https://github.com/vllm-project/vllm) for optional model inference.

See [CITATION.cff](CITATION.cff) for citing PaperWeave. Upstream tools retain
their own licenses and citation requirements.

## 📖 Project documentation

- [Implementation plan](docs/implementation_plan.md)
- [Current walkthrough](docs/walkthrough.md)
- [Web interface roadmap](docs/web_roadmap.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Release process](docs/releasing.md)

PaperWeave is released under the [MIT License](LICENSE). The license applies to
PaperWeave code, not to the papers users process.
