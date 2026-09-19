"""Unit tests for document quality assessment."""

import tempfile
import unittest
from pathlib import Path

from corpus_converter.io import write_jsonl
from corpus_converter.quality import assess_document


class QualityTest(unittest.TestCase):
    def test_assess_document_accepted(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            paper_dir = Path(tmp_dir) / "doc_123"
            paper_dir.mkdir()
            blocks = [
                {"text": "A" * 300, "heading_level": 1, "page_index": 0},
                {"text": "B" * 300, "heading_level": None, "page_index": 0},
                {"text": "C" * 300, "heading_level": None, "page_index": 1},
            ]
            write_jsonl(paper_dir / "blocks.jsonl", blocks)
            quality = assess_document(paper_dir)
            self.assertEqual(quality["status"], "accepted")
            self.assertEqual(quality["block_count"], 3)

    def test_assess_document_very_low_text_alert(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            paper_dir = Path(tmp_dir) / "doc_empty"
            paper_dir.mkdir()
            blocks = [{"text": "Short", "heading_level": None, "page_index": 0}]
            write_jsonl(paper_dir / "blocks.jsonl", blocks)
            quality = assess_document(paper_dir)
            self.assertEqual(quality["status"], "review_needed")
            self.assertIn("very_low_text", quality["reasons"])

    def test_clean_dataset_candidate_table_headers_and_prepositions(self):
        from corpus_converter.semantic import _clean_dataset_candidate

        # Preposition extractions from table/section headers
        self.assertEqual(_clean_dataset_candidate("TABLE II COMPARISON RESULTS ON THE TRANSCG"), "TransCG")
        self.assertEqual(_clean_dataset_candidate("BASELINE ON THE CLEARPOSE"), "ClearPose")
        self.assertEqual(_clean_dataset_candidate("B EVALUATIONS ON SCANNET"), "ScanNet")
        self.assertEqual(_clean_dataset_candidate("DEPTH COMPLETION RESULTS ON CLEARGRASP"), "ClearGrasp")
        self.assertEqual(_clean_dataset_candidate("Unlike the Booster"), "Booster")
        self.assertEqual(_clean_dataset_candidate("Since the TransCG"), "TransCG")

        # Acronym & variant canonicalization
        self.assertEqual(_clean_dataset_candidate("TRANS10 K"), "Trans10K")
        self.assertEqual(_clean_dataset_candidate("ClearGrasp Real"), "ClearGrasp")
        self.assertEqual(_clean_dataset_candidate("Clear-Grasp Real-novel"), "ClearGrasp")
        self.assertEqual(_clean_dataset_candidate("NYU Depth V2"), "NYUv2")
        self.assertEqual(_clean_dataset_candidate("MP3D-mesh"), "Matterport3D")

        # False positives and generic terms rejected
        for bad in [
            "All",
            "Depth",
            "Synthetic",
            "Real",
            "Real-world",
            "Evaluation",
            "Perspective",
            "Panoramic",
            "RGB",
            "RGB-D",
            "RGBD",
            "RGB-polarization",
            "Q7 Does",
            "C.1",
            "C.2",
            "TABLE II COMPARISON RESULTS",
            "DETAILS",
            "Apple",
            "Maria",
            "Tiger",
        ]:
            self.assertIsNone(_clean_dataset_candidate(bad), f"Failed to reject false positive: {bad}")

    def test_quality_report_dataset_density_warning(self):
        from corpus_converter.quality_report import generate_quality_report

        with tempfile.TemporaryDirectory() as tmp_dir:
            corpus_dir = Path(tmp_dir)
            records_dir = corpus_dir / "records"
            records_dir.mkdir(parents=True)
            # Create a mock work
            mock_work = {"work_id": "work_1", "document_ids": ["doc_1"], "title": "Test Paper"}
            mock_analysis = {"extraction_mode": "deterministic"}
            mock_exp_clean = {"datasets": [{"name": "ClearGrasp"}, {"name": "TransCG"}], "metrics": [{"name": "IoU"}]}
            mock_tax = {"facets": {}}
            report = generate_quality_report(corpus_dir, [(mock_work, mock_analysis, mock_exp_clean, mock_tax)])
            self.assertIn("Total unique datasets found across the corpus: **2**", report)
            self.assertIn("Pass", report)

            # Create high-density fake datasets (e.g. 5 datasets for 1 paper > 1.5 ratio)
            mock_exp_bloated = {"datasets": [{"name": f"FakeDS_{i}"} for i in range(5)], "metrics": [{"name": "IoU"}]}
            report_bloated = generate_quality_report(
                corpus_dir, [(mock_work, mock_analysis, mock_exp_bloated, mock_tax)]
            )
            self.assertIn("High dataset density detected", report_bloated)
            self.assertIn("Warning (High Density)", report_bloated)


if __name__ == "__main__":
    unittest.main()
