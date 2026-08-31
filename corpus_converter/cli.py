import argparse
import json
from pathlib import Path

from .adapters import normalize_non_pdf
from .io import write_json
from .providers import compute_capabilities, resolve_provider
from .reconcile import reconcile_mineru
from .evaluation import evaluate_gold
from .ingestion import ingest
from .sections import section_corpus
from .semantic import analyze_corpus, enrich_corpus, validate_evidence
from .synthesis import synthesize_corpus
from .taxonomy import classify_corpus, generate_collections


PROJECT_ROOT = Path(__file__).resolve().parent


def corpus_path(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.exists():
        raise argparse.ArgumentTypeError(f"Corpus directory does not exist: {path}")
    return path


def run_postprocess(
    corpus: Path,
    profile: str | None,
    force_normalization: bool = False,
    force_analysis: bool = False,
    provider_kind: str = "deterministic",
    model: str | None = None,
    base_url: str | None = None,
    strict_provider: bool = False,
) -> dict:
    resolution = resolve_provider(provider_kind, model, base_url, strict_provider)
    result = {
        "compute": compute_capabilities(),
        "non_pdf_normalization": normalize_non_pdf(corpus, force=force_normalization),
        "sections": section_corpus(corpus),
        "analysis": analyze_corpus(corpus, force=force_analysis),
    }
    result["semantic_provider"] = enrich_corpus(corpus, resolution, force=force_analysis)
    evidence = validate_evidence(corpus)
    if evidence["invalid"]:
        raise RuntimeError(f"Evidence validation failed: {evidence}")
    result["evidence"] = evidence
    result["taxonomy"] = classify_corpus(corpus, PROJECT_ROOT, profile)
    result["collections"] = generate_collections(corpus)
    result["synthesis"] = synthesize_corpus(corpus)
    write_json(corpus / "manifests" / "last_run.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="paperweave",
        description="Normalize, analyze, organize, and synthesize research-paper corpora.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.add_argument("--input", required=True, type=Path)
    ingest_parser.add_argument("--corpus", required=True, type=Path)
    ingest_parser.add_argument("--rename-mode", choices=["title", "keep"], default="title")
    ingest_parser.add_argument("--format-policy", choices=["prefer-pdf", "all"], default="prefer-pdf")
    ingest_parser.add_argument("--keep-duplicates-in-place", action="store_true")
    subparsers.add_parser("capabilities")
    normalize_parser = subparsers.add_parser("normalize-non-pdf")
    normalize_parser.add_argument("--corpus", required=True, type=corpus_path)
    normalize_parser.add_argument("--force", action="store_true")

    for name in ("section", "analyze", "classify", "synthesize", "postprocess", "reconcile-mineru", "evaluate"):
        command = subparsers.add_parser(name)
        command.add_argument("--corpus", required=True, type=corpus_path)
        if name in {"classify", "postprocess"}:
            command.add_argument(
                "--taxonomy-profile",
                default="core",
                help="Taxonomy path relative to taxonomies without .json, e.g. computer_vision/optical_flow.",
            )
        if name == "postprocess":
            command.add_argument("--force-normalization", action="store_true")
            command.add_argument("--force-analysis", action="store_true")
            command.add_argument(
                "--semantic-provider",
                choices=["deterministic", "ollama", "openai-compatible"],
                default="deterministic",
            )
            command.add_argument("--model")
            command.add_argument("--base-url")
            command.add_argument("--strict-provider", action="store_true")
        if name == "evaluate":
            command.add_argument("--gold", required=True, type=Path)

    args = parser.parse_args()
    if args.command == "ingest":
        input_path = args.input.expanduser().resolve()
        if not input_path.exists():
            parser.error(f"Input path does not exist: {input_path}")
        result = ingest(
            input_path,
            args.corpus.expanduser().resolve(),
            args.rename_mode,
            args.format_policy,
            not args.keep_duplicates_in_place,
        )
    elif args.command == "capabilities":
        result = compute_capabilities()
    elif args.command == "normalize-non-pdf":
        result = normalize_non_pdf(args.corpus, args.force)
    elif args.command == "evaluate":
        result = evaluate_gold(args.corpus, args.gold.expanduser().resolve())
    elif args.command == "reconcile-mineru":
        result = reconcile_mineru(args.corpus)
    elif args.command == "section":
        result = section_corpus(args.corpus)
    elif args.command == "analyze":
        result = analyze_corpus(args.corpus)
        result["evidence"] = validate_evidence(args.corpus)
    elif args.command == "classify":
        result = classify_corpus(args.corpus, PROJECT_ROOT, args.taxonomy_profile)
        result.update(generate_collections(args.corpus))
    elif args.command == "synthesize":
        result = synthesize_corpus(args.corpus)
    else:
        result = run_postprocess(
            args.corpus,
            args.taxonomy_profile,
            args.force_normalization,
            args.force_analysis,
            args.semantic_provider,
            args.model,
            args.base_url,
            args.strict_provider,
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
