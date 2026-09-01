"""Terminal-based interactive review tool for quality alerts and duplicate match candidates."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .io import read_json, read_jsonl, write_jsonl
from .manifest import load_manifest
from .merge import merge_works

logger = logging.getLogger(__name__)


def review_corpus(
    corpus: Path,
    interactive: bool = False,
    input_fn: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """Summarize review items and optionally resolve duplicate candidates one by one."""
    candidates = read_jsonl(corpus / "manifests" / "work_match_candidates.jsonl")
    duplicates = read_jsonl(corpus / "manifests" / "duplicates.jsonl")

    quality_issues = []
    for paper_dir in sorted((corpus / "papers").glob("doc_*")):
        q = read_json(paper_dir / "quality.json", {})
        if q.get("status") == "review_needed":
            quality_issues.append({"document_id": paper_dir.name, "reasons": q.get("reasons", [])})

    pending_candidates = [item for item in candidates if item.get("status", "review_needed") == "review_needed"]
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        console.print("\n[bold cyan]═══ PaperWeave Corpus Review ═══[/bold cyan]\n")

        # Quality table
        if quality_issues:
            q_table = Table(title="Documents Requiring Quality Review", title_style="bold red")
            q_table.add_column("Document ID", style="cyan")
            q_table.add_column("Reasons", style="yellow")
            for item in quality_issues:
                q_table.add_row(item["document_id"], ", ".join(item["reasons"]))
            console.print(q_table)
            console.print()
        else:
            console.print("[green]✓ No quality warnings found in normalized documents.[/green]\n")

        # Work match candidates table
        if pending_candidates:
            c_table = Table(title="Fuzzy Work-Match Candidates (Potential Duplicates)", title_style="bold yellow")
            c_table.add_column("Left Doc", style="cyan")
            c_table.add_column("Left Title", style="white")
            c_table.add_column("Right Doc", style="cyan")
            c_table.add_column("Right Title", style="white")
            c_table.add_column("Sim", style="green")
            for item in pending_candidates:
                c_table.add_row(
                    item.get("left_document_id", "")[:12],
                    item.get("left_title", "")[:35],
                    item.get("right_document_id", "")[:12],
                    item.get("right_title", "")[:35],
                    str(item.get("similarity", "")),
                )
            console.print(c_table)
            console.print()
        else:
            console.print("[green]✓ No ambiguous fuzzy title matches found.[/green]\n")

    except ImportError:
        # Fallback to plain stdout
        print("=== PaperWeave Corpus Review ===")
        print(f"Quality review needed: {len(quality_issues)} documents")
        for item in quality_issues:
            print(f"  - {item['document_id']}: {', '.join(item['reasons'])}")
        print(f"Fuzzy work-match candidates: {len(pending_candidates)} pairs")
        for item in pending_candidates:
            print(f"  - [{item.get('similarity')}] '{item.get('left_title')}' vs '{item.get('right_title')}'")

    merged = rejected = skipped = 0
    interactive_completed = False
    if interactive:
        if input_fn is None and not sys.stdin.isatty():
            logger.warning("Interactive review requires a terminal; no candidate decisions were changed.")
        else:
            prompt = input_fn or input
            manifest = {record["document_id"]: record for record in load_manifest(corpus)}
            for item in pending_candidates:
                question = (
                    "\nPotential same work:\n"
                    f"  A: {item.get('left_title')}\n"
                    f"  B: {item.get('right_title')}\n"
                    f"  similarity: {item.get('similarity')}\n"
                    "[m]erge with recoverable backup, [r]eject, [s]kip, [q]uit: "
                )
                decision = prompt(question).strip().casefold()[:1]
                if decision == "q":
                    break
                if decision == "r":
                    item["status"] = "rejected"
                    rejected += 1
                    continue
                if decision != "m":
                    skipped += 1
                    continue

                left = manifest.get(item.get("left_document_id"))
                right = manifest.get(item.get("right_document_id"))
                if not left or not right or left["work_id"] == right["work_id"]:
                    item["status"] = "invalid_or_already_resolved"
                    skipped += 1
                    continue
                if merge_works(corpus, left["work_id"], right["work_id"], reason="interactive_human_confirmation"):
                    item["status"] = "merged"
                    merged += 1
                    manifest = {record["document_id"]: record for record in load_manifest(corpus)}
                else:
                    item["status"] = "merge_failed"
                    skipped += 1
            write_jsonl(corpus / "manifests" / "work_match_candidates.jsonl", candidates)
            interactive_completed = True

    return {
        "quality_review_needed": len(quality_issues),
        "fuzzy_candidates": len(pending_candidates),
        "exact_duplicates": len(duplicates),
        "interactive_completed": interactive_completed,
        "merged": merged,
        "rejected": rejected,
        "skipped": skipped,
    }
