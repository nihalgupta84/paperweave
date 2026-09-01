"""Command-line interface for PaperWeave."""

import argparse
import json
import logging
from pathlib import Path

from . import __version__
from .adapters import normalize_non_pdf
from .evaluation import evaluate_gold
from .ingestion import ingest
from .io import write_json
from .logging_config import setup_logging
from .providers import compute_capabilities, resolve_provider
from .reconcile import reconcile_mineru
from .sections import section_corpus
from .semantic import analyze_corpus, enrich_corpus, validate_evidence
from .synthesis import synthesize_incremental
from .taxonomy import classify_corpus, generate_collections

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent


def corpus_path(value: str) -> Path:
    """Validate and resolve a corpus directory argument."""
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
    entities_path: str | None = None,
) -> dict:
    """Run all postprocessing stages on an existing corpus."""
    resolution = resolve_provider(provider_kind, model, base_url, strict_provider)
    result = {
        "compute": compute_capabilities(),
        "non_pdf_normalization": normalize_non_pdf(corpus, force=force_normalization),
        "sections": section_corpus(corpus),
        "analysis": analyze_corpus(corpus, force=force_analysis, entities_path=entities_path),
    }
    result["semantic_provider"] = enrich_corpus(corpus, resolution, force=force_analysis)
    evidence = validate_evidence(corpus)
    if evidence["invalid"]:
        raise RuntimeError(f"Evidence validation failed: {evidence}")
    result["evidence"] = evidence
    result["taxonomy"] = classify_corpus(corpus, PROJECT_ROOT, profile)
    result["collections"] = generate_collections(corpus)
    result["synthesis"] = synthesize_incremental(corpus)
    from .citation_graph import build_knowledge_graph
    from .retrieval import build_search_index

    result["graph"] = build_knowledge_graph(corpus)
    result["search_index"] = build_search_index(corpus)
    write_json(corpus / "manifests" / "last_run.json", result)
    return result


def main() -> None:
    """PaperWeave CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="paperweave",
        description="Normalize, analyze, organize, and synthesize research-paper corpora.",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show DEBUG-level log messages.")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress INFO-level log messages.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── ingest ──────────────────────────────────────────────────────
    ingest_parser = subparsers.add_parser("ingest", help="Discover, deduplicate, and stage documents.")
    ingest_parser.add_argument("--input", required=True, type=Path)
    ingest_parser.add_argument("--corpus", required=True, type=Path)
    ingest_parser.add_argument("--rename-mode", choices=["title", "keep"], default="title")
    ingest_parser.add_argument("--format-policy", choices=["prefer-pdf", "all"], default="prefer-pdf")
    ingest_parser.add_argument("--keep-duplicates-in-place", action="store_true")
    ingest_parser.add_argument("--dry-run", action="store_true", help="Show planned actions without modifying files.")

    # ── capabilities ────────────────────────────────────────────────
    subparsers.add_parser("capabilities", help="Show system capabilities (GPU, Ollama, etc.).")

    # ── normalize-non-pdf ───────────────────────────────────────────
    normalize_parser = subparsers.add_parser("normalize-non-pdf", help="Normalize DOCX/HTML documents.")
    normalize_parser.add_argument("--corpus", required=True, type=corpus_path)
    normalize_parser.add_argument("--force", action="store_true")

    # ── stage-specific subcommands ──────────────────────────────────
    for name in ("section", "analyze", "classify", "synthesize", "postprocess", "reconcile-mineru", "evaluate"):
        command = subparsers.add_parser(name)
        command.add_argument("--corpus", required=True, type=corpus_path)
        if name in {"classify", "postprocess"}:
            command.add_argument(
                "--taxonomy-profile",
                default="core",
                help="Taxonomy path relative to taxonomies without .json, e.g. computer_vision/optical_flow.",
            )
        if name in {"analyze", "postprocess"}:
            command.add_argument(
                "--entities",
                default=None,
                help="Path to custom entities.json file (datasets/metrics lists).",
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

    # ── export ──────────────────────────────────────────────────────
    export_parser = subparsers.add_parser("export", help="Export corpus to BibTeX, CSV, or JSON-LD.")
    export_parser.add_argument("--corpus", required=True, type=corpus_path)
    export_parser.add_argument("--format", required=True, choices=["bibtex", "csv", "jsonld"], dest="export_format")
    export_parser.add_argument("--output", required=True, type=Path, help="Output file path.")

    # ── review ──────────────────────────────────────────────────────
    review_parser = subparsers.add_parser("review", help="Summarize items needing review.")
    review_parser.add_argument("--corpus", required=True, type=corpus_path)
    review_parser.add_argument("--interactive", action="store_true", help="Accept/reject review items interactively.")

    # ── citation-graph ──────────────────────────────────────────────
    cg_parser = subparsers.add_parser(
        "citation-graph", help="Build in-corpus citation graph from extracted references."
    )
    cg_parser.add_argument("--corpus", required=True, type=corpus_path)
    cg_parser.add_argument("--related-threshold", type=float, default=0.16)
    cg_parser.add_argument("--related-per-paper", type=int, default=5)

    graph_parser = subparsers.add_parser("graph", help="Build paper and heterogeneous knowledge graphs.")
    graph_parser.add_argument("--corpus", required=True, type=corpus_path)

    grobid_parser = subparsers.add_parser("grobid", help="Enrich PDF metadata and references with GROBID.")
    grobid_parser.add_argument("--corpus", required=True, type=corpus_path)
    grobid_parser.add_argument("--base-url", default="http://127.0.0.1:8070")
    grobid_parser.add_argument("--force", action="store_true")
    grobid_parser.add_argument("--strict", action="store_true", help="Fail when GROBID is unavailable.")

    index_parser = subparsers.add_parser("index", help="Build the local lexical and vector search index.")
    index_parser.add_argument("--corpus", required=True, type=corpus_path)

    search_parser = subparsers.add_parser("search", help="Search normalized corpus blocks locally.")
    search_parser.add_argument("--corpus", required=True, type=corpus_path)
    search_parser.add_argument("query")
    search_parser.add_argument("--mode", choices=["hybrid", "lexical", "vector"], default="hybrid")
    search_parser.add_argument("--limit", type=int, default=10)

    # ── merge ───────────────────────────────────────────────────────
    merge_parser = subparsers.add_parser("merge", help="Merge fuzzy work-match candidates.")
    merge_parser.add_argument("--corpus", required=True, type=corpus_path)
    merge_parser.add_argument("--auto", action="store_true", help="Auto-merge above threshold.")
    merge_parser.add_argument("--threshold", type=float, default=0.95, help="Similarity threshold for auto-merge.")

    args = parser.parse_args()
    setup_logging(verbose=args.verbose, quiet=args.quiet)

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
            dry_run=args.dry_run,
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
        result = analyze_corpus(args.corpus, entities_path=getattr(args, "entities", None))
        result["evidence"] = validate_evidence(args.corpus)
    elif args.command == "classify":
        result = classify_corpus(args.corpus, PROJECT_ROOT, args.taxonomy_profile)
        result.update(generate_collections(args.corpus))
    elif args.command == "synthesize":
        result = synthesize_incremental(args.corpus)
    elif args.command == "export":
        from .export import export_bibtex, export_csv, export_jsonld

        exporters = {"bibtex": export_bibtex, "csv": export_csv, "jsonld": export_jsonld}
        result = exporters[args.export_format](args.corpus, args.output)
    elif args.command == "review":
        from .review import review_corpus

        result = review_corpus(args.corpus, interactive=args.interactive)
    elif args.command == "citation-graph":
        from .citation_graph import build_citation_graph

        result = build_citation_graph(
            args.corpus, related_threshold=args.related_threshold, related_per_paper=args.related_per_paper
        )
    elif args.command == "graph":
        from .citation_graph import build_knowledge_graph

        result = build_knowledge_graph(args.corpus)
    elif args.command == "grobid":
        from .grobid import enrich_corpus_with_grobid

        result = enrich_corpus_with_grobid(args.corpus, args.base_url, args.force, args.strict)
    elif args.command == "index":
        from .retrieval import build_search_index

        result = build_search_index(args.corpus)
    elif args.command == "search":
        from .retrieval import search_corpus

        result = search_corpus(args.corpus, args.query, args.limit, args.mode)
    elif args.command == "merge":
        from .merge import auto_merge_candidates, merge_interactive

        if args.auto:
            result = auto_merge_candidates(args.corpus, args.threshold)
        else:
            result = merge_interactive(args.corpus)
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
            entities_path=getattr(args, "entities", None),
        )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
