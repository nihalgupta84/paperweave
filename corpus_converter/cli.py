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
SOURCE_DIRECTORY_NAMES = {"pdfs", "raw_pdfs"}


def default_corpus_directory(input_value: str) -> Path:
    """Choose a non-nested corpus location for a local input when omitted."""
    candidate = Path(input_value).expanduser()
    if candidate.exists():
        candidate = candidate.resolve()
        directory = candidate if candidate.is_dir() else candidate.parent
        if directory.name.casefold() in SOURCE_DIRECTORY_NAMES:
            return directory.parent
    return (Path.cwd() / "corpus").resolve()


def render_run_summary(result: dict) -> str:
    """Render a concise human-readable result for the normal CLI path."""
    corpus = Path(result["corpus"])
    ingestion = result.get("ingestion", {})
    postprocess = result.get("postprocess", {})
    semantic = postprocess.get("semantic_provider", {})
    graph = postprocess.get("graph", {})
    cleanup = result.get("parser_cleanup", {})
    model = semantic.get("model") or "deterministic extraction"
    lines = [
        "",
        "PaperWeave completed",
        f"  Papers:   {ingestion.get('works', 0)} works ({ingestion.get('documents', 0)} documents)",
        f"  Reports:  {corpus / 'synthesis'}",
        f"  Search:   {corpus / 'indexes' / 'search.sqlite3'}",
        f"  Graph:    {graph.get('paper_nodes', 0)} papers, {graph.get('internal_citations', 0)} citations, "
        f"{graph.get('related_paper_links', 0)} related links",
        f"  Analysis: {model}",
    ]
    if cleanup.get("removed_document_folders"):
        lines.append(f"  Cleanup:  removed parser intermediates for {cleanup['removed_document_folders']} documents")
    log_path = result.get("mineru", {}).get("log")
    if log_path:
        lines.append(f"  Log:      {log_path}")
    return "\n".join(lines)


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

    # ── package-native end-to-end workflow ─────────────────────────
    run_parser = subparsers.add_parser("run", help="Run the complete workflow from documents to reports.")
    run_parser.add_argument("input_path", nargs="?", help="Local file/folder or Google Drive folder URL/ID.")
    run_parser.add_argument("--input", dest="input_option", help=argparse.SUPPRESS)
    run_parser.add_argument(
        "--corpus",
        "--corpus-dir",
        type=Path,
        dest="corpus",
        help="Output directory. Defaults to ./corpus or the parent of a pdfs/raw_pdfs folder.",
    )
    run_parser.add_argument("--remote", help="rclone remote for Google Drive input.")
    run_parser.add_argument("--device", choices=["auto", "gpu", "cpu"], default="auto")
    run_parser.add_argument("--backend", default="pipeline", help="MinerU backend.")
    run_parser.add_argument("--method", default="auto", help="MinerU parsing method.")
    run_parser.add_argument("--rename-mode", choices=["title", "keep"], default="title")
    run_parser.add_argument("--format-policy", choices=["prefer-pdf", "all"], default="prefer-pdf")
    run_parser.add_argument("--taxonomy-profile", default="core")
    run_parser.add_argument(
        "--semantic-provider",
        choices=["auto", "deterministic", "ollama", "openai-compatible"],
        default="auto",
    )
    run_parser.add_argument("--model")
    run_parser.add_argument("--base-url", help="OpenAI-compatible model endpoint.")
    run_parser.add_argument("--strict-provider", action="store_true")
    run_parser.add_argument("--grobid-url", help="Optional GROBID service URL.")
    run_parser.add_argument("--strict-grobid", action="store_true")
    run_parser.add_argument("--force", action="store_true", help="Rerun extraction, normalization, and analysis.")
    run_parser.add_argument("--force-mineru", action="store_true")
    run_parser.add_argument("--force-normalization", action="store_true")
    run_parser.add_argument("--force-analysis", action="store_true")
    run_parser.add_argument("--keep-parser-output", action="store_true", help="Retain MinerU intermediate files.")
    run_parser.add_argument("--mineru-path", help="Path to compatible MinerU (3.x) executable.")
    run_parser.add_argument("--assets", choices=["figures", "all", "none"], default="none")
    run_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")

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

    compact_parser = subparsers.add_parser("compact", help="Remove retained parser intermediates safely.")
    compact_parser.add_argument("--corpus", required=True, type=corpus_path)
    compact_parser.add_argument("--assets", choices=["figures", "all", "none"], default="none")

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
            command.add_argument(
                "--force",
                action="store_true",
                help="Force re-analysis of all documents.",
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

    if args.command == "run":
        from .pipeline import run_pipeline

        try:
            input_value = args.input_path or args.input_option
            if not input_value:
                parser.error("paperweave run requires a file or folder, for example: paperweave run papers")
            corpus = args.corpus or default_corpus_directory(input_value)
            result = run_pipeline(
                input_value,
                corpus,
                remote=args.remote,
                device=args.device,
                backend=args.backend,
                method=args.method,
                rename_mode=args.rename_mode,
                format_policy=args.format_policy,
                taxonomy_profile=args.taxonomy_profile,
                semantic_provider=args.semantic_provider,
                model=args.model,
                base_url=args.base_url,
                strict_provider=args.strict_provider,
                grobid_url=args.grobid_url,
                strict_grobid=args.strict_grobid,
                force_mineru=args.force or args.force_mineru,
                force_normalization=args.force or args.force_normalization,
                force_analysis=args.force or args.force_analysis,
                keep_parser_output=args.keep_parser_output,
                mineru_path=args.mineru_path,
                asset_policy=args.assets,
                stream_parser_output=args.verbose,
            )
        except (FileNotFoundError, RuntimeError, ValueError) as error:
            parser.exit(2, f"paperweave: error: {error}\n")
    elif args.command == "ingest":
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
    elif args.command == "compact":
        from .pipeline import compact_corpus

        result = compact_corpus(args.corpus, args.assets)
    elif args.command == "normalize-non-pdf":
        result = normalize_non_pdf(args.corpus, args.force)
    elif args.command == "evaluate":
        result = evaluate_gold(args.corpus, args.gold.expanduser().resolve())
    elif args.command == "reconcile-mineru":
        result = reconcile_mineru(args.corpus)
    elif args.command == "section":
        result = section_corpus(args.corpus)
    elif args.command == "analyze":
        result = analyze_corpus(args.corpus, force=args.force, entities_path=getattr(args, "entities", None))
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
    if args.command == "run" and not args.json:
        print(render_run_summary(result))
    else:
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
