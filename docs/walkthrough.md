# PaperWeave Walkthrough

## Current Goal

Convert project-local research documents into a clean, reusable corpus that supports
evidence-backed literature analysis without nested output folders or duplicated
PDF category trees.

## Current Phase

End-to-end open-source MVP implemented and verified, including multi-format
ingestion, pre-extraction deduplication, model fallback, and failure isolation.

## Pipeline

```text
PDF/DOCX/HTML -> dedup/work selection -> parser adapter -> normalized papers -> sections -> records
     -> taxonomy -> collections -> five synthesis reports
```

The trusted extraction layer is deterministic and extractive. Rich model-authored
narrative synthesis remains optional rather than being mixed into source records.

## Key Decisions

- `corpus/pdfs` is the canonical input path.
- `corpus/raw/mineru` preserves parser output.
- `corpus/papers/<document_id>` is the clean document store.
- SHA-256-derived document IDs are stable across title corrections.
- Exact normalized-title matches share a work ID; fuzzy matches remain explicit
  review candidates rather than being merged automatically.
- Taxonomy folders will be generated views, not physical PDF organization.
- Graph and vector-database integrations are deferred until structured records
  and evidence validation are reliable.

## Immediate Acceptance Test

Completed on synthetic MinerU v2 fixtures and a real legacy MinerU 3.4.0 corpus.
The real run normalized 12 papers and 2,782 blocks, validated 746 evidence
references with zero invalid references, generated 19 collections, and wrote all
five synthesis reports.

## Next Steps

1. Review taxonomy aliases and extracted reports for the target research domain.
2. Add another domain taxonomy only when a project requires it.
3. Evaluate the optional structured-output enrichment against a manually
   annotated gold corpus before relying on inferred claims in a paper.
