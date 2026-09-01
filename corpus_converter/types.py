"""Typed dictionary definitions for PaperWeave data structures.

These provide documentation and IDE support for the dict-heavy pipeline
without requiring a full class refactor.
"""

from __future__ import annotations

from typing import Any, TypedDict


class EvidenceLocator(TypedDict):
    """A pointer to a specific block within a document."""

    document_id: str
    block_id: str
    page_index: int | None
    section: str


class Statement(TypedDict):
    """An extracted claim or observation with provenance."""

    statement: str
    support_status: str  # includes "evidence_cited_unverified" for model-generated statements
    evidence: list[EvidenceLocator]


class BlockSource(TypedDict):
    """Parser provenance for a normalized block."""

    parser: str  # "mineru" | "docx" | "html"
    parser_version: str | None
    source_file: str | None
    source_index: int


class DocumentBlock(TypedDict):
    """A normalized document block (paragraph, heading, image, etc.)."""

    block_id: str
    document_id: str
    type: str
    heading_level: int | None
    page_index: int | None
    section_path: list[str]
    text: str
    bbox: list[float] | None
    asset_path: str | None
    source: BlockSource


class SectionedBlock(DocumentBlock):
    """A block with section role assigned."""

    section_role: str


class DocumentRecord(TypedDict, total=False):
    """Canonical document metadata stored in ``document.json``."""

    document_id: str
    work_id: str
    sha256: str | None
    format: str
    version: str
    title: str
    authors: list[str]
    year: int | None
    doi: str | None
    arxiv_id: str | None
    source_path: str | None
    parser: dict[str, Any]
    block_count: int
    asset_count: int


class WorkRecord(TypedDict, total=False):
    """A scholarly work (potentially with multiple document versions)."""

    schema_version: str
    work_id: str
    title: str
    authors: list[str]
    year: int | None
    doi: str | None
    arxiv_id: str | None
    document_ids: list[str]
    merge_status: str


class AnalysisRecord(TypedDict, total=False):
    """Structured analysis of a document's scientific content."""

    schema_version: str
    work_id: str
    document_id: str
    extraction_mode: str
    research_problem: list[Statement]
    methodology: list[Statement]
    contributions: list[Statement]
    method_components: list[Statement]
    training_objectives: list[Statement]
    limitations: list[Statement]
    claims: list[Statement]


class ExperimentRecord(TypedDict, total=False):
    """Structured extraction of a document's experimental details."""

    schema_version: str
    work_id: str
    document_id: str
    datasets: list[dict[str, Any]]
    metrics: list[dict[str, Any]]
    baselines: list[dict[str, Any]]
    implementation_details: list[Statement]
    results: list[Statement]
    ablations: list[Statement]


class TaxonomyAssignment(TypedDict):
    """A single facet assignment from taxonomy classification."""

    id: str
    name: str
    status: str
    source: str
    evidence: list[EvidenceLocator]


class TaxonomyRecord(TypedDict):
    """Faceted taxonomy classification for a work."""

    schema_version: str
    work_id: str
    profile: str
    facets: dict[str, list[TaxonomyAssignment]]


class ManifestRecord(TypedDict, total=False):
    """A row in the corpus manifest (``documents.jsonl``)."""

    document_id: str
    work_id: str
    sha256: str
    title: str
    title_key: str
    format: str
    source_path: str
    canonical_path: str
    file_name: str
    file_size: int
    selected_for_extraction: bool
    extractable: bool
    selection_reason: str
    year: int | None
    authors: list[str]
    preflight: dict[str, Any]
    stages: dict[str, dict[str, Any]]
    created_at: str


class ReferenceEntry(TypedDict, total=False):
    """A single extracted bibliographic reference."""

    raw: str
    index: int
    parsed_title: str | None
    parsed_authors: list[str]
    parsed_year: int | None
    evidence: EvidenceLocator
