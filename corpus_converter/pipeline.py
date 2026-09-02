"""Package-native end-to-end PaperWeave workflow."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .grobid import enrich_corpus_with_grobid
from .ingestion import ingest
from .io import read_json, write_json
from .manifest import load_manifest, save_manifest
from .mineru import format_mineru_output
from .reconcile import reconcile_mineru

logger = logging.getLogger(__name__)

DRIVE_FOLDER = re.compile(r"(?:folders/|[?&]id=)([A-Za-z0-9_-]+)")
DRIVE_ID = re.compile(r"^[A-Za-z0-9_-]{20,}$")
MIME_SUFFIX = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/html": ".html",
}


def _run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """Run a subprocess and raise a readable error on failure."""
    try:
        return subprocess.run(command, check=True, text=True, **kwargs)
    except FileNotFoundError as error:
        raise RuntimeError(f"Required command is not installed: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "").strip()
        suffix = f"\n{detail}" if detail else ""
        raise RuntimeError(f"Command failed ({error.returncode}): {' '.join(command)}{suffix}") from error


def _drive_folder_id(value: str) -> str | None:
    match = DRIVE_FOLDER.search(value)
    if match:
        return match.group(1)
    return value if DRIVE_ID.fullmatch(value) else None


def download_google_drive(value: str, output: Path, remote: str | None = None) -> dict[str, Any]:
    """Download supported documents from a Google Drive folder using rclone."""
    if not shutil.which("rclone"):
        raise RuntimeError(
            "Google Drive input requires rclone. Install and configure rclone, "
            "then retry with --remote NAME when more than one remote exists."
        )
    folder_id = _drive_folder_id(value)
    if not folder_id:
        raise ValueError(f"Not a Google Drive folder URL or ID: {value}")
    if remote:
        remote = remote.rstrip(":")
    else:
        listed = _run(["rclone", "listremotes"], capture_output=True).stdout.splitlines()
        remotes = [item.rstrip(":") for item in listed if item.strip()]
        if len(remotes) != 1:
            raise RuntimeError("Configure exactly one rclone remote or pass --remote NAME.")
        remote = remotes[0]

    listing = _run(
        [
            "rclone",
            "lsjson",
            f"{remote}:",
            "--drive-root-folder-id",
            folder_id,
            "--files-only",
            "--recursive",
        ],
        capture_output=True,
    )
    try:
        entries = json.loads(listing.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("rclone returned invalid JSON while listing Google Drive.") from error

    selected = []
    for entry in entries:
        remote_path = str(entry.get("Path", ""))
        mime_type = str(entry.get("MimeType", ""))
        suffix = MIME_SUFFIX.get(mime_type)
        if not suffix and Path(remote_path).suffix.casefold() not in {".pdf", ".docx", ".html", ".htm"}:
            continue
        target = output / remote_path
        if suffix and target.suffix.casefold() not in {suffix, ".htm" if suffix == ".html" else suffix}:
            target = target.with_name(f"{target.name}{suffix}")
        target.parent.mkdir(parents=True, exist_ok=True)
        _run(
            [
                "rclone",
                "copyto",
                f"{remote}:{remote_path}",
                str(target),
                "--drive-root-folder-id",
                folder_id,
                "--transfers",
                "1",
                "--checkers",
                "4",
            ]
        )
        if not target.is_file() or target.stat().st_size == 0:
            raise RuntimeError(f"Downloaded file is missing or empty: {target}")
        selected.append(str(target))
    if not selected:
        raise RuntimeError("No PDF, DOCX, or HTML documents were found in the Google Drive folder.")
    return {"remote": remote, "folder_id": folder_id, "documents": len(selected), "paths": selected}


def _mineru_version(command: str) -> str | None:
    try:
        output = subprocess.run([command, "--version"], check=False, text=True, capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"\d+(?:\.\d+)+", f"{output.stdout} {output.stderr}")
    return match.group(0) if match else None


def run_mineru(
    corpus: Path,
    device: str = "auto",
    backend: str = "pipeline",
    method: str = "auto",
    force: bool = False,
    stream_output: bool = False,
) -> dict[str, Any]:
    """Run MinerU for selected PDFs that do not already have raw output."""
    corpus = corpus.resolve()
    raw_output = corpus / "raw" / "mineru"
    logs = corpus / "logs"
    raw_output.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    reconcile_mineru(corpus)
    selected = [
        record
        for record in load_manifest(corpus)
        if record.get("selected_for_extraction") and record.get("format") == "pdf"
    ]
    pending = []
    for record in selected:
        normalized = corpus / "papers" / record["document_id"] / ".done"
        mineru_complete = record.get("stages", {}).get("mineru", {}).get("status") == "complete"
        if force or (not normalized.is_file() and not mineru_complete):
            pending.append(record)
    if not selected:
        return {"status": "not_needed", "selected_pdfs": 0, "processed": 0}
    if not pending:
        return {"status": "already_complete", "selected_pdfs": len(selected), "processed": 0}

    command = shutil.which("mineru")
    if not command:
        raise RuntimeError(
            "PDF extraction requires MinerU, but the 'mineru' command is unavailable. "
            "Install the PDF workflow with: pip install 'paperweave[full]'\n"
            "DOCX/HTML-only corpora work with the base paperweave package."
        )
    environment = os.environ.copy()
    if device == "cpu":
        environment["CUDA_VISIBLE_DEVICES"] = ""

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    log_path = logs / f"mineru_batch_{timestamp}.log"
    with tempfile.TemporaryDirectory(prefix="paperweave-mineru-") as temporary:
        input_dir = Path(temporary)
        for record in pending:
            source = Path(record["canonical_path"])
            if not source.is_absolute():
                source = corpus / source
            if not source.is_file():
                raise RuntimeError(f"Selected PDF is missing: {source}")
            destination = input_dir / source.name
            if destination.exists():
                destination = input_dir / f"{record['document_id']}_{source.name}"
            destination.symlink_to(source.resolve())
        mineru_command = [command, "-p", str(input_dir), "-o", str(raw_output), "-b", backend, "-m", method]
        logger.info("Running MinerU for %d PDF(s); log: %s", len(pending), log_path)
        with log_path.open("w", encoding="utf-8") as log_handle:
            process = subprocess.Popen(
                mineru_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=environment,
                bufsize=1,
            )
            assert process.stdout is not None
            for line in process.stdout:
                if stream_output:
                    print(line, end="")
                log_handle.write(line)
            return_code = process.wait()

    reconciliation = reconcile_mineru(corpus)
    if return_code and reconciliation["complete"] == 0:
        raise RuntimeError(f"MinerU failed with exit code {return_code}. See {log_path}")
    return {
        "status": "complete" if return_code == 0 else "partial",
        "selected_pdfs": len(selected),
        "processed": len(pending),
        "processed_document_ids": [record["document_id"] for record in pending],
        "return_code": return_code,
        "log": str(log_path),
        "reconciliation": reconciliation,
        "version": _mineru_version(command),
    }


def prune_mineru_output(corpus: Path, document_ids: list[str]) -> dict[str, int]:
    """Remove newly generated MinerU intermediates after successful normalization."""
    raw_root = (corpus / "raw" / "mineru").resolve()
    manifest = load_manifest(corpus)
    records = {record.get("document_id"): record for record in manifest}
    removed = 0
    for document_id in document_ids:
        if not (corpus / "papers" / document_id / ".done").is_file():
            continue
        record = records.get(document_id, {})
        raw_value = record.get("stages", {}).get("mineru", {}).get("raw_directory")
        if not raw_value:
            continue
        raw_path = Path(raw_value).resolve()
        paper_root = raw_path.parent if raw_path.name == "auto" else raw_path
        if paper_root.parent != raw_root or not paper_root.is_dir():
            continue
        shutil.rmtree(paper_root)
        document_path = corpus / "papers" / document_id / "document.json"
        document = read_json(document_path, {})
        if document:
            document.setdefault("parser", {})["raw_directory"] = None
            document["parser"]["raw_retained"] = False
            write_json(document_path, document)
        stage = record.setdefault("stages", {}).setdefault("mineru", {})
        stage["raw_directory"] = None
        stage["raw_retained"] = False
        removed += 1
    if manifest:
        save_manifest(corpus, manifest)
    for directory in (raw_root, raw_root.parent):
        with suppress(OSError):
            directory.rmdir()
    return {"removed_document_folders": removed}


def compact_corpus(corpus: Path, asset_policy: str = "none") -> dict[str, Any]:
    """Compact an existing corpus while preserving canonical papers and evidence."""
    corpus = corpus.expanduser().resolve()
    raw_root = corpus / "raw" / "mineru"
    normalization = {"done": 0, "skipped": 0, "failed": 0}
    if raw_root.is_dir():
        reconcile_mineru(corpus)
        normalization = format_mineru_output(corpus_dir=corpus, force=True, asset_policy=asset_policy)
    document_ids = [
        record["document_id"]
        for record in load_manifest(corpus)
        if record.get("format") == "pdf" and record.get("selected_for_extraction")
    ]
    cleanup = prune_mineru_output(corpus, document_ids)
    return {"corpus": str(corpus), "asset_policy": asset_policy, "normalization": normalization, "cleanup": cleanup}


def run_pipeline(
    input_value: str,
    corpus: Path,
    *,
    remote: str | None = None,
    device: str = "auto",
    backend: str = "pipeline",
    method: str = "auto",
    rename_mode: str = "title",
    format_policy: str = "prefer-pdf",
    taxonomy_profile: str = "core",
    semantic_provider: str = "auto",
    model: str | None = None,
    base_url: str | None = None,
    strict_provider: bool = False,
    grobid_url: str | None = None,
    strict_grobid: bool = False,
    force_mineru: bool = False,
    force_normalization: bool = False,
    force_analysis: bool = False,
    keep_parser_output: bool = False,
    asset_policy: str = "none",
    stream_parser_output: bool = False,
) -> dict[str, Any]:
    """Run the complete installed-package workflow for local or Drive input."""
    corpus = corpus.expanduser().resolve()

    local_candidate = Path(input_value).expanduser()
    if local_candidate.exists():
        drive = None
        input_path = local_candidate.resolve()
        if input_path.is_dir() and (input_path == corpus or input_path in corpus.parents):
            raise ValueError(
                f"Output cannot be inside the input folder ({corpus}). "
                f"Choose a sibling location, for example: --corpus {input_path.parent}"
            )
        corpus.mkdir(parents=True, exist_ok=True)
    elif _drive_folder_id(input_value):
        corpus.mkdir(parents=True, exist_ok=True)
        drive = download_google_drive(input_value, corpus / "downloaded", remote)
        input_path = corpus / "downloaded"
    else:
        drive = None
        input_path = local_candidate.resolve()
        raise FileNotFoundError(f"Input path does not exist: {input_path}")

    result: dict[str, Any] = {
        "input": str(input_path),
        "corpus": str(corpus),
        "drive": drive,
        "ingestion": ingest(input_path, corpus, rename_mode, format_policy),
    }
    result["mineru"] = run_mineru(corpus, device, backend, method, force_mineru, stream_output=stream_parser_output)
    raw_mineru_exists = (corpus / "raw" / "mineru").is_dir()
    if result["mineru"].get("processed", 0) or raw_mineru_exists:
        result["normalization"] = format_mineru_output(
            corpus_dir=corpus,
            parser_version=result["mineru"].get("version"),
            force=force_normalization,
            asset_policy=asset_policy,
        )
    else:
        result["normalization"] = {"done": 0, "skipped": 0, "failed": 0}
    if not keep_parser_output and result["mineru"].get("processed_document_ids"):
        result["parser_cleanup"] = prune_mineru_output(corpus, result["mineru"]["processed_document_ids"])
    if grobid_url:
        result["grobid"] = enrich_corpus_with_grobid(corpus, grobid_url, force_normalization, strict_grobid)

    from .cli import run_postprocess

    result["postprocess"] = run_postprocess(
        corpus,
        taxonomy_profile,
        force_normalization,
        force_analysis,
        semantic_provider,
        model,
        base_url,
        strict_provider,
    )
    write_json(corpus / "manifests" / "last_pipeline.json", result)
    return result
