# Getting started

## 1. Install

For PDF, DOCX, and HTML:

```bash
python -m pip install "paperweave[full]"
```

For DOCX and HTML only:

```bash
python -m pip install paperweave
```

Inside an activated virtual or Conda environment, do not add `--user`; doing so
can place the executable outside the active environment.

## 2. Run

From a project containing a `papers/` folder:

```bash
paperweave run papers
```

If papers are already under `corpus/raw_pdfs/`:

```bash
paperweave run corpus/raw_pdfs
```

Both commands produce a corpus with reports under `corpus/synthesis/`.

## 3. Read the results

Start with:

1. `corpus/synthesis/datasets.md`
2. `corpus/synthesis/methodology.md`
3. `corpus/synthesis/experiments.md`
4. `corpus/synthesis/literature_review.md`

Statements ending in a locator such as
`doc_abcd…:blk_1234…:p5` identify the supporting document block and PDF page.

## 4. Add more papers

Place additional documents in the source folder and run the same command.
Completed papers are reused; new and incomplete papers are processed.

## Common choices

Use deterministic extraction only:

```bash
paperweave run papers --semantic-provider deterministic
```

Keep no extracted images:

```bash
paperweave run papers --assets none
```

Retain all MinerU debugging output:

```bash
paperweave run papers --assets all --keep-parser-output --verbose
```

Print structured pipeline status for automation:

```bash
paperweave run papers --json
```
