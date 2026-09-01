"""Enforced JSON Schema validation for PaperWeave records."""

from __future__ import annotations

import json
from functools import cache
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator


class RecordValidationError(ValueError):
    """Raised when a canonical PaperWeave record violates its runtime schema."""


@cache
def _validator(schema_name: str) -> Draft202012Validator:
    schema_path = files("corpus_converter").joinpath("schemas", f"{schema_name}.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_record(data: dict[str, Any], schema_name: str) -> list[str]:
    """Validate a record and raise a detailed exception when any constraint fails."""
    errors = sorted(_validator(schema_name).iter_errors(data), key=lambda error: list(error.absolute_path))
    rendered = []
    for error in errors:
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        rendered.append(f"{location}: {error.message}")
    if rendered:
        raise RecordValidationError(f"Invalid {schema_name} record: {'; '.join(rendered)}")
    return []


def validate_document(data: dict[str, Any]) -> list[str]:
    """Enforce the canonical document schema."""
    return validate_record(data, "document")


def validate_work(data: dict[str, Any]) -> list[str]:
    """Enforce the canonical scholarly-work schema."""
    return validate_record(data, "work")


def validate_block(data: dict[str, Any]) -> list[str]:
    """Enforce the normalized document-block schema."""
    return validate_record(data, "document_block")


def validate_analysis(data: dict[str, Any]) -> list[str]:
    """Enforce the analysis-record schema."""
    return validate_record(data, "analysis")


def validate_experiments(data: dict[str, Any]) -> list[str]:
    """Enforce the experiment-record schema."""
    return validate_record(data, "experiment")


def validate_taxonomy(data: dict[str, Any]) -> list[str]:
    """Enforce the taxonomy-record schema."""
    return validate_record(data, "taxonomy")
