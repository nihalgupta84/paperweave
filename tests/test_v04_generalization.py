"""Tests for PaperWeave v0.4 generalization improvements."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from corpus_converter.ingestion import author_surnames, title_key
from corpus_converter.io import read_json, write_json, write_jsonl
from corpus_converter.quality_report import write_quality_report
from corpus_converter.semantic import (
    _clean_dataset_candidate,
    discover_metric_mentions,
    rebuild_work_aggregates,
)
from corpus_converter.synthesis import write_datasets


class GeneralizationPhaseOneTests(unittest.TestCase):
    """Phase 1: Dataset false-positive rejection."""

    def test_demonstrative_and_stopword_rejection(self):
        for candidate in ["Although", "This", "These", "Those", "However", "Moreover", "Furthermore"]:
            self.assertIsNone(_clean_dataset_candidate(candidate), f"Failed to reject: {candidate}")

    def test_sentence_boundary_leak_rejection(self):
        for candidate in ["Data. Considering", "Results. The", "Benchmark. Our"]:
            self.assertIsNone(_clean_dataset_candidate(candidate), f"Failed to reject: {candidate}")

    def test_modality_and_anatomy_rejection(self):
        for candidate in ["CT", "MRI", "PET", "X-ray", "Abdominal", "Clinical"]:
            self.assertIsNone(_clean_dataset_candidate(candidate), f"Failed to reject: {candidate}")

    def test_section_title_prefix_rejection(self):
        for candidate in ["Construction of CARE", "Description of WORD", "Overview of MSD"]:
            self.assertIsNone(_clean_dataset_candidate(candidate), f"Failed to reject: {candidate}")

    def test_prepositional_leak_rejection(self):
        for candidate in ["In the clinical setting", "From our private", "In the large scale", "At the initial"]:
            self.assertIsNone(_clean_dataset_candidate(candidate), f"Failed to reject: {candidate}")

    def test_valid_dataset_candidates_accepted(self):
        valid = ["ImageNet", "WORD", "MSD", "Synapse", "BTCV", "TotalSegmentator", "Cityscapes"]
        for candidate in valid:
            cleaned = _clean_dataset_candidate(candidate)
            self.assertIsNotNone(cleaned, f"Wrongly rejected valid dataset: {candidate}")
            self.assertEqual(cleaned, candidate)

        # Prepositional wrapper correctly stripped to extract core dataset
        self.assertEqual(_clean_dataset_candidate("In the BTCV"), "BTCV")
        self.assertEqual(_clean_dataset_candidate("From the ImageNet"), "ImageNet")


class GeneralizationPhaseTwoTests(unittest.TestCase):
    """Phase 2: Preprint/journal auto-merge and title normalization."""

    def test_title_key_subtitle_stripping(self):
        t1 = "U-SAM: High-Performance Segment Anything Model for Medical Images"
        t2 = "U-SAM"
        self.assertEqual(title_key(t1), title_key(t2))

        t3 = "A Novel Architecture for Segmentation — Evaluation on Clinical CT"
        t4 = "A Novel Architecture for Segmentation"
        self.assertEqual(title_key(t3), title_key(t4))

    def test_author_surnames_extraction(self):
        authors_strings = ["John Doe", "Jane A. Smith", "Robert van der Meer"]
        self.assertEqual(author_surnames(authors_strings), {"doe", "smith", "meer"})

        authors_dicts = [{"name": "Alice Johnson"}, {"name": "Bob Williams"}]
        self.assertEqual(author_surnames(authors_dicts), {"johnson", "williams"})

    def test_aggregate_deduplication(self):
        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary)
            doc1_id = "doc_0123456789abcdef"
            doc2_id = "doc_fedcba9876543210"
            work_id = "work_0123456789abcdef"
            blk1 = "blk_00000000000000000001"
            blk2 = "blk_00000000000000000002"
            blk3 = "blk_00000000000000000003"

            (record_dir / "documents" / doc1_id).mkdir(parents=True)
            (record_dir / "documents" / doc2_id).mkdir(parents=True)

            ev1 = {"document_id": doc1_id, "block_id": blk1, "page_index": 0, "section": "Methods"}
            ev2 = {"document_id": doc1_id, "block_id": blk2, "page_index": 0, "section": "Results"}
            ev3 = {"document_id": doc2_id, "block_id": blk3, "page_index": 1, "section": "Methods"}

            doc1_analysis = {
                "schema_version": "1.0",
                "work_id": work_id,
                "document_id": doc1_id,
                "extraction_mode": "deterministic_extractive",
                "research_problem": [
                    {"statement": "Accurate rectal segmentation.", "support_status": "supported", "evidence": [ev1]}
                ],
                "methodology": [],
                "contributions": [{"statement": "Proposed U-SAM.", "support_status": "supported", "evidence": [ev2]}],
                "method_components": [],
                "training_objectives": [],
                "limitations": [],
                "claims": [],
            }
            doc2_analysis = {
                "schema_version": "1.0",
                "work_id": work_id,
                "document_id": doc2_id,
                "extraction_mode": "deterministic_extractive",
                "research_problem": [
                    {
                        "statement": "Accurate rectal segmentation.",
                        "support_status": "supported",
                        "evidence": [ev1, ev3],
                    }
                ],
                "methodology": [],
                "contributions": [{"statement": "Proposed U-SAM.", "support_status": "supported", "evidence": [ev2]}],
                "method_components": [],
                "training_objectives": [],
                "limitations": [],
                "claims": [],
            }
            doc1_exp = {
                "schema_version": "1.0",
                "work_id": work_id,
                "document_id": doc1_id,
                "datasets": [{"name": "WORD", "evidence": []}],
                "metrics": [],
                "baselines": [],
                "implementation_details": [],
                "results": [],
                "ablations": [],
            }
            doc2_exp = {
                "schema_version": "1.0",
                "work_id": work_id,
                "document_id": doc2_id,
                "datasets": [{"name": "word", "evidence": []}],
                "metrics": [],
                "baselines": [],
                "implementation_details": [],
                "results": [],
                "ablations": [],
            }

            write_json(record_dir / "documents" / doc1_id / "analysis.json", doc1_analysis)
            write_json(record_dir / "documents" / doc2_id / "analysis.json", doc2_analysis)
            write_json(record_dir / "documents" / doc1_id / "experiments.json", doc1_exp)
            write_json(record_dir / "documents" / doc2_id / "experiments.json", doc2_exp)

            work = {"work_id": work_id, "document_ids": [doc1_id, doc2_id]}
            rebuild_work_aggregates(record_dir, work)

            agg_analysis = read_json(record_dir / "analysis.json", {})
            self.assertEqual(len(agg_analysis["research_problem"]), 1)
            # Richer evidence (2 items) was kept
            self.assertEqual(len(agg_analysis["research_problem"][0]["evidence"]), 2)

            agg_experiments = read_json(record_dir / "experiments.json", {})
            self.assertEqual(len(agg_experiments["datasets"]), 1)


class GeneralizationPhaseThreeTests(unittest.TestCase):
    """Phase 3: Domain-agnostic metric auto-discovery."""

    def test_metric_auto_discovery_patterns(self):
        doc_id = "doc_0123456789abcdef"
        blocks = [
            {
                "document_id": doc_id,
                "section_role": "results",
                "type": "paragraph",
                "block_id": "blk_00000000000000000001",
                "page_index": 0,
                "text": "The model achieved DSC of 0.895 and HD95 of 4.2mm on the test split. We also noted ASD: 1.25.",
            },
            {
                "document_id": doc_id,
                "section_role": "results",
                "type": "paragraph",
                "block_id": "blk_00000000000000000002",
                "page_index": 0,
                "text": "Baseline scores: 85.2% Dice and 91.0% mIoU. Notice TABLE 1 and FIG 2 show GPU memory.",
            },
        ]
        found, all_names = discover_metric_mentions(blocks, ("accuracy", "precision"))
        names = {item["name"] for item in found}
        self.assertIn("DSC", names)
        self.assertIn("HD95", names)
        self.assertIn("ASD", names)
        self.assertIn("mIoU", names)
        # Blocklisted non-metrics
        self.assertNotIn("TABLE", names)
        self.assertNotIn("FIG", names)
        self.assertNotIn("GPU", names)


class GeneralizationPhaseFourTests(unittest.TestCase):
    """Phase 4: Synthesis deduplication and corpus statistics."""

    def test_dataset_synthesis_deduplication(self):
        with tempfile.TemporaryDirectory() as temporary:
            corpus = Path(temporary)
            (corpus / "synthesis").mkdir(parents=True)
            work1 = {"work_id": "work_1", "title": "Paper One", "document_ids": ["doc_1"]}
            experiments1 = {"datasets": [{"name": "WORD", "evidence": []}]}
            taxonomy1 = {"facets": {"dataset": [{"name": "word"}]}}

            work2 = {"work_id": "work_2", "title": "Paper Two", "document_ids": ["doc_2"]}
            experiments2 = {"datasets": [{"name": "WORD", "evidence": []}]}
            taxonomy2 = {"facets": {}}

            records = [(work1, {}, experiments1, taxonomy1), (work2, {}, experiments2, taxonomy2)]
            write_datasets(corpus, records)

            content = (corpus / "synthesis" / "datasets.md").read_text()
            # "## WORD" should appear exactly once
            self.assertEqual(content.count("## WORD"), 1)
            # Both works cited under it
            self.assertIn("Paper One", content)
            self.assertIn("Paper Two", content)


class GeneralizationPhaseFiveTests(unittest.TestCase):
    """Phase 5: Quality report generation and self-audit."""

    def test_quality_report_detects_and_formats(self):
        with tempfile.TemporaryDirectory() as temporary:
            corpus = Path(temporary)
            (corpus / "synthesis").mkdir(parents=True)
            (corpus / "manifests").mkdir(parents=True)
            doc_id = "doc_0123456789abcdef"
            work_id = "work_0123456789abcdef"
            (corpus / "papers" / doc_id).mkdir(parents=True)

            # Create mock section and paper
            write_jsonl(
                corpus / "papers" / doc_id / "sections.jsonl",
                [{"document_id": doc_id, "block_id": "b1", "page_index": 0, "section_path": ["Results"]}],
            )
            work = {
                "work_id": work_id,
                "title": "Clinical Study on Rectal Segmentation",
                "document_ids": [doc_id, f"{doc_id}_preprint"],
            }
            analysis = {
                "extraction_mode": "deterministic_extractive",
                "research_problem": [],
            }
            experiments = {
                "metrics": [{"name": "DSC"}],
                "results": [
                    {
                        "statement": "Achieved DSC of 0.89.",
                        "evidence": [{"document_id": doc_id, "block_id": "b1", "page_index": 0}],
                    }
                ],
                "datasets": [{"name": "WORD"}],
            }
            taxonomy = {"facets": {}}
            records = [(work, analysis, experiments, taxonomy)]

            report_path = write_quality_report(corpus, records)
            self.assertTrue(report_path.is_file())
            content = report_path.read_text()

            self.assertIn("Corpus Quality Audit Report", content)
            self.assertIn("Total Scholarly Works | 1", content)
            self.assertIn("Total Document Representations | 2", content)
            self.assertIn("Multi-document works (1)", content)
            self.assertIn("No suspicious dataset names detected", content)
            self.assertIn("Works with extracted metrics: **1/1**", content)
            self.assertIn("`deterministic_extractive`: 1 work(s)", content)


if __name__ == "__main__":
    unittest.main()
