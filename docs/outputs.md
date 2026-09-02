# Understanding PaperWeave output

PaperWeave separates files meant for reading from files needed for reproducible
processing.

## Read these first

`synthesis/` contains corpus-level reports:

| File | Contents |
| --- | --- |
| `datasets.md` | Dataset names and papers that use them |
| `methodology.md` | Research problems and method descriptions |
| `experiments.md` | Experimental setup, metrics, and reported results |
| `literature_review.md` | Faceted cross-paper overview |
| `references.md` | Extracted bibliography entries |
| `all_papers.md` | Combined normalized paper text |
| `citation_graph.md` | Human-readable paper graph summary |

`papers/<document_id>/paper.md` is the clean Markdown for one document.

## Source and generated data

| Directory | Purpose | Normally inspect? |
| --- | --- | --- |
| `pdfs/` | Organized source PDFs | Sometimes |
| `papers/` | Normalized text and selected media | Yes |
| `synthesis/` | Corpus reports | Yes |
| `collections/` | Generated faceted indexes | Yes |
| `records/` | Structured work, evidence, experiment, and graph data | For automation |
| `indexes/` | Local search database | No |
| `manifests/` | IDs, deduplication, and stage state | For diagnostics |
| `logs/` | Detailed parser logs | When a run fails |
| `raw/` | Optional retained parser output | Only with `--keep-parser-output` |

## Storage policies

The default `--assets none` creates a compact text corpus. Tables and captions
remain searchable text. `--assets figures` retains captioned figure/table
assets, while `--assets all` keeps every parser image and can create many files
because some equations are rendered as images.

New MinerU intermediate output is removed after successful normalization unless
`--keep-parser-output` is set. The source PDF, normalized Markdown, structured
blocks, selected assets, evidence records, and parser log remain available.

For an older corpus that still contains all MinerU intermediates, run:

```bash
paperweave compact --corpus corpus
```

Compaction first rebuilds normalized assets according to `--assets`, then
removes a parser document folder only when its normalized document is complete.

## IDs and evidence

`document_id` identifies one exact file. `work_id` identifies the scholarly work
that may have PDF, DOCX, HTML, preprint, or accepted-manuscript representations.

Evidence locators use:

```text
document_id:block_id:page
```

This lets a user or downstream agent trace an extracted statement back to its
normalized source block.
