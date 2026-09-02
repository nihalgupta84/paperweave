# 📚 PaperWeave

> Turn research papers into a clean, searchable, evidence-linked literature corpus.

[![CI](https://github.com/nihalgupta84/paperweave/actions/workflows/ci.yml/badge.svg)](https://github.com/nihalgupta84/paperweave/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/paperweave?color=3776AB&label=PyPI)](https://pypi.org/project/paperweave/)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-2EA44F)](LICENSE)

PaperWeave takes one paper or a folder of papers and produces:

- deduplicated and normalized documents;
- corpus reports about methods, experiments, datasets, and references;
- exact and semantic-style local search;
- evidence links back to document blocks and pages;
- citation, related-paper, and paper–dataset knowledge graphs.

PDF, DOCX, HTML, and HTM inputs are supported. An LLM is optional.

## Quick start

Install PDF support:

```bash
python -m pip install "paperweave[full]"
```

Run it from your project directory:

```bash
paperweave run papers
```

That is the complete workflow. Results are written to `corpus/`.

If your documents already live in `corpus/raw_pdfs` or `corpus/pdfs`, use:

```bash
paperweave run corpus/raw_pdfs
```

PaperWeave recognizes these source-folder names and uses their parent as the
corpus directory. You can always choose an explicit destination:

```bash
paperweave run /path/to/papers --corpus /path/to/corpus
```

For DOCX/HTML without PDF extraction, the smaller installation is enough:

```bash
python -m pip install paperweave
```

## What the command does

```text
discover → deduplicate → extract → identify sections → analyze
         → organize → synthesize → index → build graphs
```

Re-running the command processes new or incomplete papers and reuses completed
work.

The normal terminal output is a short completion summary. MinerU’s detailed
output is saved to a log instead of flooding the terminal. Use `--verbose` to
watch parser output or `--json` for a machine-readable result.

## Outputs you will normally use

```text
corpus/
├── pdfs/                         organized source PDFs
├── papers/<document_id>/         normalized paper Markdown
├── synthesis/
│   ├── methodology.md            methods across papers
│   ├── experiments.md            setups, metrics, and results
│   ├── datasets.md               datasets and papers using them
│   ├── literature_review.md      faceted corpus overview
│   ├── references.md             extracted bibliographies
│   ├── citation_graph.md         readable graph explanation
│   └── all_papers.md             combined normalized text
├── collections/                  generated topic/method/dataset views
└── indexes/search.sqlite3        local search index
```

The `records/` and `manifests/` directories are machine-readable internal data
that make reports reproducible. Most users do not need to open them.

By default, PaperWeave produces a compact text corpus: it keeps source PDFs,
Markdown, tables as text, evidence records, and reports, while removing parser
intermediates and extracted image files. Retain selected or all visuals when
needed:

```bash
paperweave run papers --assets figures
paperweave run papers --assets all --keep-parser-output
```

Compact parser files retained by an older release:

```bash
paperweave compact --corpus corpus
```

See [Understanding the output](docs/outputs.md) for the complete layout.

## Automatic local LLM selection

The default `--semantic-provider auto` follows this order:

1. If Ollama is running and `llm-checker` is installed, ask `llm-checker` to
   rank the models already installed on this hardware.
2. Use its highest-ranked available model for evidence-constrained enrichment.
3. If no suitable local model is available, complete the run with deterministic
   extraction.

PaperWeave never downloads a large model silently. To enable automatic model
selection:

```bash
npm install -g llm-checker
ollama serve
paperweave run papers
```

To select a model yourself:

```bash
paperweave run papers --semantic-provider ollama --model qwen2.5:7b
```

To prohibit LLM use:

```bash
paperweave run papers --semantic-provider deterministic
```

`llm-checker` is optional and remains governed by its own license. PaperWeave
uses only its installed-model ranking; it does not automatically pull or remove
models.

## Search

```bash
paperweave search --corpus corpus "rectal cancer segmentation datasets"
```

Search combines exact-term retrieval with a lightweight local vector-like
ranking. It works without an external database or model.

## Understanding the graphs

PaperWeave creates two related graph views:

- **paper graph** — papers connected by extracted citations or explainable
  similarity;
- **knowledge graph** — papers connected to datasets and taxonomy labels.

Citation links are marked as identifier-verified or fuzzy-title candidates.
Related-paper links are computed only from the papers in your corpus. PaperWeave
does not search the global literature like Connected Papers or Litmaps.

Read [Understanding graphs](docs/graphs.md) for edge meanings, confidence, and
GraphML visualization instructions.

## Mixed folders and duplicates

| Input situation | Behavior |
| --- | --- |
| One supported file | Process that file |
| Nested directory | Find supported papers recursively |
| Exact duplicate | Process once and record the duplicate |
| PDF, DOCX, and HTML of the same paper | Group as one work; prefer PDF |
| Distinct manuscript versions | Keep separate documents under one work when identity is supported |
| Images, CSV, source code, logs, or archives | Ignore them as paper inputs |
| Unreadable or protected PDF | Isolate the failure and continue |

Use `--format-policy all` when every distinct representation should be parsed.

## Google Drive

After configuring an rclone Google Drive remote:

```bash
paperweave run "https://drive.google.com/drive/folders/FOLDER_ID" --remote mydrive
```

## Useful options

```text
--corpus PATH                    choose the corpus directory
--device auto|gpu|cpu            MinerU compute device
--assets figures|all|none        normalized visual assets to retain
--keep-parser-output             keep MinerU intermediate/debug output
--semantic-provider auto|deterministic|ollama|openai-compatible
--model NAME                     explicitly select a model
--verbose                        show detailed processing output
--json                           print the full machine-readable run result
--force-analysis                 rebuild extracted facts and reports
```

Run `paperweave run --help` for the complete reference.

## Install for development

```bash
git clone https://github.com/nihalgupta84/paperweave.git
cd paperweave
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -e ".[full,dev]"
pre-commit run --all-files
python -m unittest discover -s tests -v
```

## Why PaperWeave?

Reference managers store papers. Document parsers convert files. Chat-with-PDF
tools answer questions. PaperWeave builds a reusable local research corpus that
connects these stages while retaining evidence provenance.

It is designed for inspectable literature work, not as a replacement for a
formal PRISMA review manager or a global scholarly search engine.

## Acknowledgements

PaperWeave uses or interoperates with [MinerU](https://github.com/opendatalab/MinerU),
[GROBID](https://github.com/kermitt2/grobid),
[rclone](https://github.com/rclone/rclone),
[Ollama](https://github.com/ollama/ollama),
[vLLM](https://github.com/vllm-project/vllm), and optionally
[LLM Checker](https://github.com/signerless/llm-checker).

Upstream projects retain their own licenses and citation requirements. Do not
redistribute papers or extracted media unless their licenses permit it.

## Documentation

- [Getting started](docs/getting_started.md)
- [Understanding the output](docs/outputs.md)
- [Understanding graphs](docs/graphs.md)
- [Implementation plan](docs/implementation_plan.md)
- [Current walkthrough](docs/walkthrough.md)
- [Web roadmap](docs/web_roadmap.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)

PaperWeave is released under the [MIT License](LICENSE).
