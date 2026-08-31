# PaperWeave

PaperWeave is an evidence-backed research-paper corpus tool. It turns a file or
mixed folder of papers into clean documents, structured records, faceted
collections, and literature-review reports.

Recommended repository name: `paperweave`
Recommended PyPI/package name: `paperweave`
Recommended command: `paperweave`

The current Python implementation keeps the internal `corpus_converter` module
name for compatibility. `corpus-converter` remains an alias command.

PaperWeave accepts PDF, DOCX, and HTML papers from Google Drive or local storage
and produces normalized papers, provenance-linked blocks, structured records,
faceted collections, and corpus-level Markdown reports.

Ingestion deduplicates before extraction, assigns document/work identities, renames canonical files from detected titles, and selects the best available representation. MinerU processes PDFs; standard-library adapters process DOCX and HTML.

---

## Features

- Supports Google Drive folder links.
- Supports Google Drive folder IDs.
- Supports a single PDF, DOCX, HTML, or HTM file.
- Recursively supports mixed folders containing multiple document formats.
- Skips unrelated CSV, image, archive, and office files with an audit log.
- Deduplicates exact bytes before extraction and recoverably quarantines in-corpus duplicates.
- Groups exact normalized titles as one work and retains distinct document versions.
- Prefers PDF over DOCX over HTML for equivalent representations by default.
- Copies files only; no symlinks are created.
- Renames canonical documents from detected titles by default.
- Runs MinerU once on the full PDF folder for faster batch extraction.
- Uses SHA-256-derived stable document IDs.
- Converts MinerU output into normalized Markdown and JSONL content blocks.
- Detects canonical paper sections while retaining original headings.
- Generates extractive methodology, experiment, dataset, and claim records with block-level evidence.
- Organizes papers through multi-valued taxonomy facets instead of duplicate folders.
- Produces `methodology.md`, `experiments.md`, `datasets.md`, `literature_review.md`, and `all_papers.md`.
- Keeps logs and manifests for status tracking and reproducibility.
- Works without an LLM; unavailable semantic providers fall back transparently to deterministic extraction.

---

## Final Output Layout

```text
target_corpus/
├── pdfs/
├── sources/
│   ├── docx/
│   └── html/
├── quarantine/
│   ├── duplicates/
│   └── unreadable/
├── raw/
│   └── mineru/
├── papers/
│   └── doc_<hash>/
│       ├── paper.md
│       ├── blocks.jsonl
│       ├── document.json
│       ├── quality.json
│       ├── assets/
│       └── .done
├── records/
│   └── work_<hash>/
│       ├── work.json
│       ├── analysis.json
│       ├── experiments.json
│       └── taxonomy.json
├── collections/                  # Generated faceted indexes
├── synthesis/
│   ├── methodology.md
│   ├── experiments.md
│   ├── datasets.md
│   ├── literature_review.md
│   └── all_papers.md
├── logs/
└── manifests/
    ├── documents.jsonl
    ├── duplicates.jsonl
    ├── work_match_candidates.jsonl
    └── last_run.json
```

The principal literature-review outputs are:

```text
target_corpus/synthesis
```

---

## Project Structure

```text
paperweave/
├── README.md
├── pyproject.toml
├── LICENSE
├── CONTRIBUTING.md
├── SECURITY.md
├── CITATION.cff
├── .gitignore
├── environment.yml
├── requirements-extra.txt
├── scripts/
│   ├── 00_check_system.py
│   ├── 01_prepare_inputs.py
│   ├── 02_download_gdrive_rclone.sh
│   ├── 03_run_mineru_batch.sh
│   ├── 04_format_mineru_output.py
│   ├── 05_run_all.sh
│   ├── 06_build_knowledge.py
│   └── 99_status.sh
├── corpus_converter/
├── schemas/
├── docs/
├── tests/
└── examples/
    └── run_example.sh
```

---

## Quick start

For DOCX/HTML processing and deterministic CPU analysis:

```bash
git clone https://github.com/nihalgupta84/paperweave.git
cd paperweave
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
paperweave ingest --input /path/to/papers --corpus /path/to/project/corpus
paperweave normalize-non-pdf --corpus /path/to/project/corpus
paperweave postprocess --corpus /path/to/project/corpus --taxonomy-profile core
```

For PDF extraction with MinerU, install the complete optional stack:

```bash
python -m pip install -e ".[full]"
```

Then run the complete pipeline:

```bash
bash scripts/05_run_all.sh \
  --input /path/to/papers \
  --corpus-dir /path/to/project/corpus \
  --device auto \
  --rename-mode title \
  --format-policy prefer-pdf
```

Or use the installation helper:

```bash
bash scripts/install.sh full
```

`full` installs MinerU and PDF dependencies. `pdf` installs only PDF metadata
dependencies. `minimal` installs the package without optional parser packages.
After this repository is published to PyPI, the equivalent user installation
will be `python -m pip install "paperweave[full]"`.

## Requirements

- Linux server, Ubuntu, or WSL environment.
- Optional NVIDIA GPU for faster MinerU inference.
- `rclone` is required only when using Google Drive input.
- Python 3.10 or newer.
- `pip` and a virtual environment are sufficient for installation.
- GPU is optional. CPU mode and deterministic analysis work without CUDA.
- `rclone` and `jq` are required only for the Google Drive downloader.

The legacy Conda files remain available for existing MinerU environments, but
new users should use the pip extras above. A GPU is not required for DOCX,
HTML, or deterministic analysis.

---

## Setup

### 1. Go to the project directory

```bash
cd paperweave
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

### 3. Install Python packages

```bash
python -m pip install -e ".[full]"
```

### 4. Check the system

```bash
python scripts/00_check_system.py
```

If GPU is required, run:

```bash
python scripts/00_check_system.py --require-gpu
```

---

## Optional: GPU configuration

If `torch.cuda.is_available()` is `False`, install the PyTorch wheel that matches your CUDA driver.

### CUDA 12.8

```bash
python -m pip uninstall -y torch torchvision torchaudio triton xformers
python -m pip freeze | grep -E '^nvidia-.*-cu13' | cut -d= -f1 | xargs -r python -m pip uninstall -y

python -m pip install --no-cache-dir \
  torch torchvision torchaudio \
  --index-url https://download.pytorch.org/whl/cu128
```

### CPU fallback

```bash
python -m pip install --no-cache-dir \
  torch torchvision torchaudio \
  --index-url https://download.pytorch.org/whl/cpu
```

Verify again:

```bash
python scripts/00_check_system.py
```

---

## Google Drive Setup with rclone

Use this section only if your documents are stored in Google Drive.

### 1. Install rclone

```bash
curl -fsSL https://rclone.org/install.sh | bash
rclone version
```

### 2. Configure the Google Drive remote

```bash
rclone config
```

Recommended choices:

```text
n
name> amity
Storage> drive
client_id> press Enter
client_secret> press Enter
scope> 2
root_folder_id> press Enter
service_account_file> press Enter
Edit advanced config? n
Use auto config? n
```

On a server without browser access, choose manual authentication. Run the generated `rclone authorize` command on your local machine with browser access, then paste the returned token back into the server.

### 3. Check the remote

```bash
rclone lsd amity:
```

If you use a different remote name, replace `amity` in all commands with your own rclone remote name.

---

## Usage

### Option A: Convert a Google Drive folder

```bash
cd paperweave

bash scripts/05_run_all.sh \
  --input "https://drive.google.com/drive/folders/YOUR_FOLDER_ID?usp=sharing" \
  --corpus-dir /workspace/projects/my_project/corpus \
  --remote amity \
  --device gpu \
  --rename-mode title
```

### Option B: Convert a local mixed folder

```bash
cd paperweave

bash scripts/05_run_all.sh \
  --input /path/to/local/document_folder \
  --corpus-dir /workspace/projects/my_project/corpus \
  --device gpu \
  --rename-mode title
```

### Option C: Convert a single local document

```bash
cd paperweave

bash scripts/05_run_all.sh \
  --input /path/to/paper.pdf \
  --corpus-dir /workspace/projects/my_project/corpus \
  --device gpu \
  --rename-mode title
```

### Option D: Run in CPU mode

```bash
bash scripts/05_run_all.sh \
  --input /path/to/local/document_folder \
  --corpus-dir /workspace/projects/my_project/corpus \
  --device cpu \
  --rename-mode title
```

---

## Step-by-Step Usage

Use these commands when you want to run each stage manually.

### 1. Prepare documents and deduplicate

```bash
python scripts/01_prepare_inputs.py \
  --input /path/to/document_folder \
  --corpus-dir /workspace/projects/my_project/corpus \
  --rename-mode title
```

This recursively scans supported documents, quarantines exact duplicates, skips
unrelated files, selects the preferred representation for each work, and
creates stable document IDs in:

```text
/workspace/projects/my_project/corpus/pdfs
/workspace/projects/my_project/corpus/manifests/documents.jsonl
```

### 2. Download Google Drive documents (optional)

```bash
bash scripts/02_download_gdrive_rclone.sh \
  "https://drive.google.com/drive/folders/YOUR_FOLDER_ID?usp=sharing" \
  /workspace/projects/my_project/corpus/downloaded \
  amity
```

### 3. Run MinerU on the full PDF folder (PDFs only)

```bash
bash scripts/03_run_mineru_batch.sh \
  --corpus-dir /workspace/projects/my_project/corpus \
  --device gpu
```

MinerU output will be saved to the raw PDF output directory. DOCX and HTML
documents bypass MinerU and are normalized by the built-in adapters.

MinerU output will be saved to:

```text
/workspace/projects/my_project/corpus/raw/mineru
```

### 4. Format the final corpus

```bash
python scripts/04_format_mineru_output.py \
  --corpus-dir /workspace/projects/my_project/corpus \
  --force
```

The final clean Markdown corpus will be saved to:

```text
/workspace/projects/my_project/corpus/papers
```

### 5. Build records, collections, and synthesis

```bash
python -m corpus_converter.cli postprocess \
  --corpus /workspace/projects/my_project/corpus \
  --taxonomy-profile computer_vision/optical_flow
```

Use `core` for a domain-neutral corpus. The current domain pack is
`computer_vision/optical_flow`; additional packs can be added under
`corpus_converter/taxonomies/`.

### 6. Check status

```bash
bash scripts/99_status.sh /workspace/projects/my_project/corpus
```

## Analysis Semantics

The default analyzer is deterministic and extractive. It does not invent a
narrative or infer unsupported research gaps. Every emitted statement, result,
dataset, metric, and taxonomy assignment retains document, block, page, and
section evidence where applicable.

`literature_review.md` is therefore a thematic evidence index. Use it with
`methodology.md` and `experiments.md` as grounded context for Codex, Claude, or
another semantic model. Model-authored narrative generation is intentionally
separate from the trusted extraction layer.

### Optional semantic providers and fallback

No local model or GPU is required. The default is:

```bash
--semantic-provider deterministic
```

Optional Ollama enrichment:

```bash
python -m corpus_converter.cli postprocess \
  --corpus /path/to/corpus \
  --taxonomy-profile core \
  --semantic-provider ollama \
  --model qwen2.5:7b
```

Optional OpenAI-compatible local or remote endpoint:

```bash
python -m corpus_converter.cli postprocess \
  --corpus /path/to/corpus \
  --semantic-provider openai-compatible \
  --model MODEL_NAME \
  --base-url http://127.0.0.1:8000/v1
```

If the endpoint or model is unavailable, processing continues with deterministic
analysis and records the reason in `manifests/last_run.json`. Use
`--strict-provider` to fail instead. Model-enriched facts are accepted only when
all cited block IDs exist in the normalized document.

## Input selection and duplicate policy

The default `--format-policy prefer-pdf` works at the scholarly-work level:

```text
same title as PDF + DOCX + HTML -> process distinct PDFs; retain DOCX/HTML as alternates
same title as DOCX + HTML       -> process DOCX; retain HTML as alternate
HTML only                       -> process HTML
different PDF byte versions    -> retain as separate documents under one work
exact duplicate bytes          -> process once
```

Use `--format-policy all` to normalize every distinct representation. Exact
duplicates are still removed. Fuzzy title matches are written to
`manifests/work_match_candidates.jsonl` with `review_needed`; they are never
merged automatically.

When duplicate files already reside inside the corpus, they are moved to
`quarantine/duplicates/`, not deleted. Password-protected PDFs are moved to
`quarantine/unreadable/`. Both operations are recoverable and auditable.

For the normal project layout, point `--corpus-dir` at the project’s own
`corpus/` directory. PaperWeave does not require a global corpus location:

```bash
paperweave ingest \
  --input /path/to/project/corpus/raw_pdfs \
  --corpus /path/to/project/corpus
```

This is safe to rerun after adding files. Existing exact duplicates are not
processed again, and generated reports can be rebuilt without moving PDFs into
taxonomy folders.

## Failure isolation and quality status

Each manifest record contains independent stage states for ingestion, MinerU,
normalization, sectioning, analysis, taxonomy, and synthesis. One failed paper
does not invalidate successful papers. `quality.json` reports block count,
character count, headings, empty-block fraction, pages when available, and an
`accepted` or `review_needed` status.

Stage-specific reruns are available:

```text
--force-mineru
--force-normalization
--force-analysis
--retry-failed
```

## Public-use checklist

The repository contains the code, schemas, taxonomy profiles, tests, CI, and
documentation. Keep each project’s downloaded corpus outside Git (the
generated `corpus/` workspace is ignored), because papers may have different
redistribution licenses. Commit only documents and fixtures that you are
allowed to redistribute. For a repeatable release, record the input manifest,
parser versions, selected format policy, semantic provider, and generated
reports.

The public name is **PaperWeave**. The Python import path remains
`corpus_converter` for compatibility, and both `paperweave` and
`corpus-converter` commands are supported. The GitHub repository is intended to
be `nihalgupta84/paperweave`; update links if you fork it.

## Gold-corpus evaluation

Create manually verified labels following `examples/gold_corpus.example.json`,
then run:

```bash
python -m corpus_converter.cli evaluate \
  --corpus /path/to/corpus \
  --gold /path/to/gold.json
```

The report is written to `manifests/evaluation.json`. The command evaluates
provided labels; it does not manufacture gold truth.

---

## Run in Background with nohup

Use this when processing many documents on a remote server. The example uses
the pip-installed virtual environment; replace the path if you use a legacy
Conda MinerU environment.

```bash
cd paperweave

mkdir -p /workspace/projects/my_project/corpus/logs

nohup bash -lc '
source /path/to/paperweave/.venv/bin/activate

bash scripts/05_run_all.sh \
  --input "https://drive.google.com/drive/folders/YOUR_FOLDER_ID?usp=sharing" \
  --corpus-dir /workspace/projects/my_project/corpus \
  --remote amity \
  --device gpu \
  --rename-mode title
' > /workspace/projects/my_project/corpus/logs/nohup_paperweave_$(date +%F_%H%M).log 2>&1 &

echo $!
```

---

## Monitor Progress

Tail the latest log file:

```bash
tail -f /workspace/projects/my_project/corpus/logs/nohup_paperweave_*.log
```

Check corpus status:

```bash
bash scripts/99_status.sh /workspace/projects/my_project/corpus
```

Check running processes:

```bash
ps -ef | grep -E 'mineru|05_run_all|03_run_mineru' | grep -v grep
```

---

## Notes

MinerU should run on the full folder, not one PDF at a time.

Slow method:

```text
load MinerU models -> process 1 PDF -> shutdown -> repeat
```

Fast method:

```text
load MinerU models once -> process entire pdfs folder -> shutdown
```

This project uses the fast method.

---

## Troubleshooting

### `torch.cuda.is_available()` is `False`

Install the correct PyTorch wheel for your CUDA version. For CUDA 12.8, use the CUDA 12.8 commands in the setup section.

### `rclone` remote not found

Check configured remotes:

```bash
rclone listremotes
```

If your remote name is not `amity`, replace `amity` with your actual remote name in all commands.

### No supported documents were copied

Check that the input path contains PDF, DOCX, HTML, or HTM files:

```bash
find /path/to/folder -type f \( -iname '*.pdf' -o -iname '*.docx' -o -iname '*.html' -o -iname '*.htm' \) | head
```

### MinerU is slow

Use GPU mode when available:

```bash
bash scripts/05_run_all.sh \
  --input /path/to/local/document_folder \
  --corpus-dir /workspace/projects/my_project/corpus \
  --device gpu \
  --rename-mode title
```

Also make sure MinerU is running once on the full folder instead of being restarted for each PDF.

---

## Recommended Workflow

For most projects, use the all-in-one command:

```bash
bash scripts/05_run_all.sh \
  --input /path/to/document_or_mixed_folder_or_google_drive_link \
  --corpus-dir /workspace/projects/my_project/corpus \
  --remote amity \
  --device gpu \
  --rename-mode title
```

After completion, use these reports in paper review:

```text
/my_project/corpus/synthesis
```
