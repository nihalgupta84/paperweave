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


if __name__ == "__main__":
    unittest.main()
