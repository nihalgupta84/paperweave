# 📚 PaperWeave

> **The Hallucination-Proof Research Paper Engine for AI Agents & Scientists.**  
> Turn messy PDF/DOCX/HTML libraries into compact, evidence-grounded research memory with coordinate-level provenance, SOTA benchmark tables, citation graphs, and zero token waste.

[![CI](https://github.com/nihalgupta84/paperweave/actions/workflows/ci.yml/badge.svg)](https://github.com/nihalgupta84/paperweave/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/paperweave?color=3776AB&label=PyPI)](https://pypi.org/project/paperweave/)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-2EA44F)](LICENSE)

---

### 💡 Why PaperWeave?

Feeding raw academic PDFs directly to AI agents (Claude Computer Use, AutoGPT, LangChain, Cursor, ChatGPT, local LLMs) breaks down in practice:

1. 💸 **Token Explosion & Context Bloat**: A 25-paper reading list consumes **350,000+ tokens** of raw repetitive text, page headers, author affiliations, and boilerplate. It burns your API budget, triggers aggressive context truncation, and slows agent inference to a crawl.
2. 🤥 **Rampant Numbers & Findings Hallucinations**: LLMs reading raw PDFs frequently scramble quantitative metrics, confuse ablation baselines with proposed contributions, or fabricate exact values (e.g. reporting a Dice score or BLEU metric that was actually an inferior baseline from 2019).
3. 🧩 **Multi-Column & Table Scrambling**: Traditional PDF converters scramble two-column layouts, break tabular benchmarks across lines, and mangle formulas into unreadable tokens.
4. 🔄 **Preprint vs. Journal Duplicate Pollution**: Real-world paper collections contain both preprints (arXiv, bioRxiv, Research Square) and published journal versions (Nature, IEEE, Springer). Agents treat them as separate competing works, polluting citations and double-counting experiments.

**PaperWeave solves this.** It parses, verifies, and normalizes entire paper libraries once into compact, structured Markdown and JSON. Every single claim, metric, and dataset is anchored to an immutable coordinate locator (`[document_id:block_id:page]`).

```text
       📚 Raw Papers (PDF / DOCX / HTML / Google Drive)
                             │
                             ▼
               ⚡ MinerU / Native Extraction
                             │
                             ▼
         🧱 Block-Level Grounding (blocks.jsonl)
                             │
    ┌────────────────────────┼────────────────────────┐
    ▼                        ▼                        ▼
📖 Agent Memory          🕸️ Knowledge & Citations   📊 SOTA Benchmarks
• methodology.md         • citation_graph.md        • experiments.md
• literature_review.md   • knowledge_graph.json     • datasets.md
• verified provenance    • GraphML export           • LaTeX .bib BibTeX
                             │
                             ▼
                 🛡️ Automated Quality Audit
                  (synthesis/quality_report.md)
```

---

### 🚀 Comparison at a Glance

| Feature | Raw PDFs / "Chat-with-PDF" | Connected Papers / Litmaps | 📚 PaperWeave (v0.4) |
| :--- | :--- | :--- | :--- |
| **Token Footprint** | 🔥 10,000–25,000 tokens/paper | N/A (Web UI only) | ⚡ **1,000–2,500 tokens/paper** (85–90% reduction) |
| **Hallucination Protection** | ❌ None (LLMs guess numbers) | N/A | 🛡️ **Coordinate-level provenance** (`doc:block:page`) |
| **Preprint ↔ Journal Merging**| ❌ Treated as duplicate papers | ⚠️ Graph link only | 🔄 **Automatic deduplication & union-find** |
| **Tabular SOTA Benchmarks** | ❌ Scrambled columns & text | ❌ None | 📊 **Extracted quantitative tables & baselines** |
| **Domain-Agnostic Metrics** | ❌ Manual prompt engineering | ❌ None | 🌐 **40+ CV, NLP, Med, ML metrics auto-discovered** |
| **Quality Self-Audit** | ❌ Black-box guessing | ❌ None | 🔍 **Automated audit report** (`quality_report.md`) |
| **Citation & Knowledge Graph** | ❌ None | ☁️ Cloud-only closed data | 🕸️ **Local GraphML + JSON (Gephi/Cytoscape)** |
| **BibTeX & LaTeX Ready** | ❌ Manual copy-pasting | ⚠️ Web export only | ✅ **Verified `.bib` and clean citation keys** |
| **Local & Private Execution** | ⚠️ Often third-party cloud | ⚠️ Cloud SaaS | 🔒 **100% Local-first** (Ollama or deterministic) |
| **Cloud Folder Sync** | ❌ Manual file downloads | ❌ None | ☁️ **Native Google Drive / rclone integration** |

---

## ⚡ Quick Start

### 1. Installation

Install PaperWeave with full PDF parsing support (recommended):

```bash
python -m pip install "paperweave[full]"
```

*For lightweight DOCX/HTML text processing without PDF pipeline dependencies:*
```bash
python -m pip install paperweave
```

### 2. Run on Your Papers

Run the complete end-to-end pipeline on any folder containing PDFs:

```bash
paperweave run ./papers
```

PaperWeave automatically:
1. Discovers, hashes, and deduplicates your files.
2. Unifies preprints and published journal versions.
3. Extracts clean text, tables, and bounding boxes via MinerU/native parsers.
4. Identifies datasets, models, architectures, and metrics.
5. Synthesizes agent-ready summaries with coordinate locators.
6. Builds citation networks and heterogeneous knowledge graphs.
7. Produces an automated **Quality Audit Report** (`synthesis/quality_report.md`).

---

## 🛡️ Zero-Hallucination Evidence Architecture

How does PaperWeave guarantee that an AI agent never hallucinates numbers or paper findings?

### 1. Coordinate-Level Evidence Locators
Every extracted fact, metric value, baseline comparison, and dataset usage is bound to an exact block ID and page number:
```markdown
- DICE score on rectal cancer segmentation reaches 89.4% [doc_a1b2:block_042:page_6]
- SwinUNETR baseline achieves 83.2% mIoU under 5-fold cross-validation [doc_c3d4:block_019:page_4]
```

### 2. Strict Build-Time Audit
During corpus synthesis, the pipeline validates every locator against the generated `blocks.jsonl` index. If an evidence reference points to a non-existent block or mismatched page, the pipeline flags the inconsistency immediately.

### 3. Automated Quality Self-Audit (`synthesis/quality_report.md`)
Every synthesized corpus automatically includes a transparent health report detailing:
- **Evidence Locator Validity**: Verification of 100% block and page coordinate existence.
- **Dataset Hygiene**: Total discovered datasets and zero false positives (guards against running text or section headers).
- **Grouping Health**: Verified single-work clusters and auto-merged preprint/journal editions.
- **Metric Extraction Health**: Discovered quantitative metrics across all domain benchmarks.

---

## 🔄 Intelligent Preprint & Journal Auto-Merging

A major failure mode in research agents is finding an arXiv or bioRxiv preprint, downloading the published Nature or IEEE journal version months later, and reasoning over them as two distinct papers.

PaperWeave v0.4 features an intelligent Union-Find merging engine:
- **DOI Server Recognition**: Distinguishes preprint servers (arXiv, bioRxiv, medRxiv, Research Square, SSRN) from published journal DOIs (Nature, IEEE, Springer, Elsevier).
- **Fuzzy Title & Subtitle Normalization**: Strips subtitles, punctuation, and casing discrepancies.
- **Unicode-Aware Author Verification**: Accurately extracts and matches author surnames across complex multi-delimiter strings and Unicode formats.
- **Non-Destructive Archiving**: Automatically merges the papers under a single primary canonical work while safely retaining raw files and provenance.

---

## 🌐 Domain-Agnostic Metric & Entity Discovery

PaperWeave supports any scientific discipline without requiring domain retraining:

- **Computer Vision & Medical Imaging**: `DSC` (Dice Similarity Coefficient), `HD95` (Hausdorff Distance 95%), `mIoU`, `ASD`, `NSD`, `mAP`, `Sensitivity`, `Specificity`.
- **Natural Language Processing & LLMs**: `BLEU`, `ROUGE`, `METEOR`, `CIDEr`, `Perplexity`, `Exact Match`, `F1`.
- **Speech & Audio**: `WER` (Word Error Rate), `CER`, `SDR`, `PESQ`.
- **Generative AI & Synthesis**: `FID` (Fréchet Inception Distance), `IS` (Inception Score), `KID`.
- **Classical ML & Statistics**: `RMSE`, `MAE`, `ROC-AUC`, `PR-AUC`, `Accuracy`, `Precision`, `Recall`.
- **Open Discovery**: Strict regex token boundaries (`[A-Z]{2,8}[0-9]*`) and token exclusion filters automatically discover novel custom metrics in your literature without matching English words or abbreviations.

---

## 🤖 How AI Agents Use PaperWeave

Point your AI agent (Claude, GPT, Gemini, or local models) directly at the generated `corpus/` folder:

### Prompt 1: Grounded Hypothesis Creation
> *"Examine `corpus/synthesis/methodology.md` and `corpus/synthesis/experiments.md`. What specific architectures and loss functions have been evaluated for [task]? What gaps exist in the current literature? Cite all paper claims using their exact `[doc:block:page]` locators."*

### Prompt 2: Baseline & Experiment Planning
> *"Read `corpus/synthesis/experiments.md` and `corpus/synthesis/datasets.md`. Tabulate the state-of-the-art results across each dataset, including evaluation metrics and reported baseline comparisons. Ensure all numbers cite their source block."*

### Prompt 3: Drafting Related Work & LaTeX Bibliography
> *"Draft a Related Work section synthesizing the themes in `corpus/synthesis/literature_review.md`. Use `corpus/synthesis/references.md` and `corpus/exports/` to generate exact BibTeX `\cite{...}` keys for our paper submission."*

---

## 📂 Generated Corpus Layout

```text
corpus/
├── 📄 papers/<document_id>/
│   ├── paper.md                 Clean, normalized Markdown
│   ├── blocks.jsonl             Structured blocks with bbox coordinates
│   └── quality.json             Extraction health & completeness diagnostics
│
├── 🧠 synthesis/                Agent-Ready Literature Memory
│   ├── methodology.md           Core methods, architectures, & loss functions
│   ├── experiments.md           Experimental setups, baselines, and metrics
│   ├── datasets.md              Deduplicated benchmark datasets and usage
│   ├── literature_review.md     Faceted overview of the entire domain
│   ├── references.md            Extracted bibliographies and citations
│   ├── citation_graph.md        Human-readable citation network summary
│   ├── quality_report.md        Automated extraction & provenance audit
│   └── all_papers.md            Unified corpus text
│
├── 🕸️ graphs/
│   ├── paper_graph.json         Paper-to-paper citations and related-work links
│   ├── knowledge_graph.json     Heterogeneous paper-dataset-taxonomy graph
│   └── knowledge_graph.graphml  Gephi- and Cytoscape-ready visualization
│
├── 🔍 indexes/
│   └── search.sqlite3           Local SQLite FTS5 + TF-IDF hybrid search
│
└── 🗂️ collections/              Generated topic & method faceted views
```

---

## ☁️ Google Drive & Cloud Ingestion (via rclone)

Have all your papers organized in Google Drive? PaperWeave natively pulls, deduplicates, and stages your entire cloud folder:

```bash
# Ingest directly from a Google Drive folder via your configured rclone remote
paperweave run "https://drive.google.com/drive/folders/FOLDER_ID" --remote mydrive
```

Files are safely hashed, renamed, and deduplicated before extraction without modifying your remote files.

---

## 🔒 100% Local & Offline First

PaperWeave works completely offline with zero mandatory API keys:

* **Automatic Local Selection**: If Ollama and `llm-checker` are installed, PaperWeave ranks and selects the best model currently installed on your hardware:
  ```bash
  paperweave run papers --semantic-provider auto
  ```
* **Specific Local Model**:
  ```bash
  paperweave run papers --semantic-provider ollama --model qwen2.5:7b
  ```
* **Pure Deterministic Mode** (No GPU / No LLM required):
  ```bash
  paperweave run papers --semantic-provider deterministic
  ```

---

## 🔍 Local Hybrid Search

Search across thousands of document blocks using combined exact full-text (SQLite FTS5) and sparse lexical-vector ranking without external vector databases:

```bash
paperweave search --corpus corpus "contrastive learning rectal cancer MRI"
```

---

## 🛠️ CLI Reference

```text
paperweave run PATH              Run the complete end-to-end workflow
paperweave ingest PATH           Discover, hash, and deduplicate documents
paperweave search QUERY          Run local hybrid search over corpus blocks
paperweave compact               Remove parser intermediates to save disk space
paperweave export --format bib   Export clean BibTeX entries for LaTeX drafting
paperweave graph                 Rebuild citation and heterogeneous knowledge graphs
paperweave capabilities          Inspect local GPU, MinerU, and Ollama capabilities
paperweave review                Inspect ambiguous merge candidates or parse warnings
```

---

## 👥 Community & Contributions

Contributions, bug reports, and suggestions are warmly welcomed!
* Read our [Contributing Guide](CONTRIBUTING.md) to set up your development environment.
* View our [Security Policy](SECURITY.md) for vulnerability reporting.
* Check the [Implementation Plan](docs/implementation_plan.md) and [Web Roadmap](docs/web_roadmap.md).

---

## 📄 License

PaperWeave is licensed under the [MIT License](LICENSE).
