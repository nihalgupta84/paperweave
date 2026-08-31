# Contributing to PaperWeave

## Development setup

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

MinerU is only required for PDF integration tests. DOCX/HTML normalization and
all deterministic postprocessing tests use the Python standard library.

## Pull requests

- Keep raw parser output separate from canonical records.
- Preserve block-level provenance for every accepted scientific statement.
- Add a focused test for every parser, schema, or taxonomy change.
- Do not add copyrighted papers to fixtures without redistribution permission.
- Never commit corpus workspaces, API keys, private data, or model weights.
- Report deterministic and model-enriched behavior separately.

Taxonomy additions should use stable IDs and conservative aliases. Ambiguous
terms belong in a domain profile, not the global taxonomy.
