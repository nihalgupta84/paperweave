# 📚 PaperWeave

> **The Hallucination-Proof Research Paper Engine for AI Agents & Scientists.**  
> Turn messy PDF/DOCX/HTML libraries into compact, evidence-grounded research memory with coordinate-level provenance, SOTA benchmark tables, citation graphs, and zero token waste.

[![CI](https://github.com/nihalgupta84/paperweave/actions/workflows/ci.yml/badge.svg)](https://github.com/nihalgupta84/paperweave/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/paperweave?color=3776AB&label=PyPI)](https://pypi.org/project/paperweave/)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-2EA44F)](LICENSE)

---

### 💡 Why PaperWeave?

Feeding raw academic PDFs directly to AI agents (Claude, GPT, Gemini, Cursor, AutoGPT, local LLMs) breaks down in practice:

1. 💸 **Token Explosion & Context Bloat**: 25 papers consume **350,000+ tokens** of raw repetitive boilerplate, header junk, and references. It burns API budgets, triggers truncation, and slows agent inference.
2. 🤥 **Rampant Numbers & Findings Hallucinations**: LLMs reading raw PDFs easily scramble quantitative metrics, confuse ablation baselines with proposed contributions, or fabricate exact values.
3. 🧩 **Multi-Column & Table Scrambling**: Traditional PDF converters scramble two-column layouts, break tabular benchmarks across lines, and mangle formulas into unreadable tokens.
4. 🔄 **Preprint vs. Journal Duplicate Pollution**: Real-world paper collections contain both preprints (arXiv, bioRxiv, Research Square) and published journal versions (Nature, IEEE, Springer). Agents treat them as separate competing works, polluting citations and double-counting experiments.

**PaperWeave normalizes your papers once into compact, structured Markdown and JSON.** Every claim, metric, and dataset is anchored to an immutable coordinate locator (`[document_id:block_id:page]`).

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

```bash
# Install with full PDF parsing support
python -m pip install "paperweave[full]"

# Run complete end-to-end extraction on any folder of papers
paperweave run ./papers
```

---

## 🛡️ Zero-Hallucination Evidence Architecture

### 1. Coordinate-Level Evidence Locators
Every extracted fact, quantitative metric, baseline comparison, and dataset usage is bound to an exact block ID and page number in the source PDF.

*For example, in a medical imaging project on a rectal cancer corpus, evidence extraction works like this:*
```markdown
- DICE score on rectal cancer segmentation reaches 89.4% [doc_a1b2:block_042:page_6]
- SwinUNETR baseline achieves 83.2% mIoU under 5-fold cross-validation [doc_c3d4:block_019:page_4]
```
*(The same coordinate precision applies equally across Computer Vision, NLP, Robotics, or Biology literature.)*

### 2. Strict Build-Time Audit
During corpus synthesis, the pipeline validates every locator against the generated `blocks.jsonl` index. If an evidence reference points to a non-existent block or mismatched page, the pipeline flags the inconsistency immediately.

### 3. Automated Quality Self-Audit (`synthesis/quality_report.md`)
Every synthesized corpus automatically includes a transparent health report auditing:
- **Evidence Locator Validity**: 100% verification rate of block and page coordinates.
- **Dataset Hygiene**: Total discovered datasets and zero false positives (guards against running text or section headers).
- **Grouping Health**: Verified single-work clusters and auto-merged preprint/journal editions.
- **Metric Extraction Health**: Discovered quantitative metrics across domain benchmarks.

---

## 🔄 Intelligent Preprint & Journal Auto-Merging

PaperWeave v0.4 features an intelligent Union-Find merging engine:
- **DOI Server Recognition**: Distinguishes preprint servers (arXiv, bioRxiv, medRxiv, Research Square, SSRN) from published journal DOIs (Nature, IEEE, Springer, Elsevier).
- **Fuzzy Title & Subtitle Normalization**: Strips subtitles, punctuation, and casing discrepancies.
- **Unicode-Aware Author Verification**: Accurately extracts and matches author surnames across complex multi-delimiter strings and Unicode formats.
- **Non-Destructive Archiving**: Automatically merges the papers under a single primary canonical work while safely retaining raw files and provenance.

---

## 🌐 Domain-Agnostic Metric & Entity Discovery

PaperWeave supports any scientific discipline out of the box:
- **Computer Vision & Medical Imaging**: `DSC` (Dice Similarity Coefficient), `HD95`, `mIoU`, `ASD`, `NSD`, `mAP`, `Sensitivity`, `Specificity`.
- **Natural Language Processing & LLMs**: `BLEU`, `ROUGE`, `METEOR`, `CIDEr`, `Perplexity`, `Exact Match`, `F1`.
- **Speech & Audio**: `WER` (Word Error Rate), `CER`, `SDR`, `PESQ`.
- **Generative AI & Synthesis**: `FID` (Fréchet Inception Distance), `IS` (Inception Score), `KID`.
- **Classical ML & Statistics**: `RMSE`, `MAE`, `ROC-AUC`, `PR-AUC`, `Accuracy`, `Precision`, `Recall`.
- **Open Discovery**: Strict regex token boundaries (`[A-Z]{2,8}[0-9]*`) and token exclusion filters automatically discover novel custom metrics in your literature without matching English words or abbreviations.

---

## 🤖 How AI Agents Use PaperWeave

Point your AI agent (Claude, GPT, Gemini, or local models) directly at the generated `corpus/` folder:

- **Hypothesis Creation**: *"Examine `corpus/synthesis/methodology.md` and `experiments.md`. What specific architectures and loss functions have been evaluated? What gaps exist in the current literature? Cite all claims using `[doc:block:page]`."*
- **Baseline Planning**: *"Read `corpus/synthesis/experiments.md` and `datasets.md`. Tabulate the state-of-the-art results across each dataset, including evaluation metrics and reported baseline comparisons."*
- **Related Work Drafting**: *"Draft a Related Work section synthesizing the themes in `corpus/synthesis/literature_review.md`. Use `corpus/synthesis/references.md` to generate exact BibTeX `\cite{...}` keys."*

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

Ingest papers directly from Google Drive without manual downloads:

```bash
paperweave run "https://drive.google.com/drive/folders/FOLDER_ID" --remote mydrive
```

<details>
<summary><b>⚙️ How to configure Google Drive & rclone</b> (click to expand)</summary>

1. Install rclone: `curl https://rclone.org/install.sh | sudo bash`
2. Run `rclone config` to link your Google Drive account under a remote name (e.g., `mydrive`).
3. Verify connection: `rclone lsd mydrive:`

📖 Read the complete guide: [docs/setup_rclone.md](docs/setup_rclone.md)
</details>

---

## 🔒 100% Local & Offline First

PaperWeave runs completely offline with zero mandatory API keys:

```bash
# Automatic local model ranking & execution
paperweave run ./papers --semantic-provider auto

# Or pure deterministic mode (zero GPU / zero LLM required)
paperweave run ./papers --semantic-provider deterministic
```

<details>
<summary><b>🦙 How to configure Ollama & llm-checker</b> (click to expand)</summary>

1. Install Ollama: `curl -fsSL https://ollama.com/install.sh | sh`
2. Pull a recommended model: `ollama pull qwen2.5:7b` (or `llama3.1:8b`)
3. Install model ranker: `python -m pip install llm-checker`
4. Verify local hardware capabilities: `paperweave capabilities`

📖 Read the complete guide: [docs/setup_ollama.md](docs/setup_ollama.md)
</details>

---

## 🔍 Local Hybrid Search

Search across thousands of document blocks using combined exact full-text (SQLite FTS5) and sparse lexical-vector ranking without external vector databases:

```bash
paperweave search --corpus corpus "transformer self-attention segmentation loss"
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
