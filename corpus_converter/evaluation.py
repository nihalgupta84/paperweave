"""Gold-standard corpus benchmark evaluation scoring precision, recall, and F1."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .io import read_json, write_json

logger = logging.getLogger(__name__)


def prf(predicted: set[str], expected: set[str]) -> dict[str, float]:
    """Compute precision, recall, and F1 score between predicted and expected sets."""
    true_positive = len(predicted & expected)
    precision = true_positive / len(predicted) if predicted else (1.0 if not expected else 0.0)
    recall = true_positive / len(expected) if expected else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}


def evaluate_gold(corpus: Path, gold_path: Path) -> dict[str, Any]:
    """Evaluate corpus predictions against a manually annotated gold evaluation file."""
    gold = read_json(gold_path, {})
    results = []

    for item in gold.get("documents", []):
        work_id = item["work_id"]
        record_dir = corpus / "records" / work_id
        experiments = read_json(record_dir / "experiments.json", {})
        taxonomy = read_json(record_dir / "taxonomy.json", {})

        predicted_taxonomy = {
            assignment["id"] for assignments in taxonomy.get("facets", {}).values() for assignment in assignments
        }
        predicted_datasets = {value["name"] for value in experiments.get("datasets", [])}
        predicted_metrics = {value["name"] for value in experiments.get("metrics", [])}

        results.append(
            {
                "work_id": work_id,
                "taxonomy": prf(predicted_taxonomy, set(item.get("taxonomy_ids", []))),
                "datasets": prf(predicted_datasets, set(item.get("datasets", []))),
                "metrics": prf(predicted_metrics, set(item.get("metrics", []))),
            }
        )

    summary = {
        "documents": len(results),
        "per_document": results,
        "note": "Gold labels must be manually verified; this command does not create gold truth.",
    }
    write_json(corpus / "manifests" / "evaluation.json", summary)
    logger.info("Evaluated %d documents against gold benchmark %s", len(results), gold_path)
    return summary
