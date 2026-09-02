"""Unit tests for ingestion title extraction, slugification, and duplicate handling."""

import tempfile
import unittest
from pathlib import Path

from corpus_converter.cli import default_corpus_directory
from corpus_converter.ingestion import (
    clean_title,
    discover,
    extract_title,
    extract_year_from_filename,
    slugify,
    title_key,
    valid_title,
)


class IngestionTest(unittest.TestCase):
    def test_discovery_ignores_nested_generated_corpus(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            (source / "paper.pdf").write_bytes(b"%PDF-source")
            nested = source / "corpus"
            (nested / "manifests").mkdir(parents=True)
            (nested / "manifests" / "last_pipeline.json").write_text("{}", encoding="utf-8")
            (nested / "pdfs").mkdir()
            (nested / "pdfs" / "duplicate.pdf").write_bytes(b"%PDF-source")
            supported, _ = discover(source)
            self.assertEqual(supported, [source / "paper.pdf"])

    def test_default_corpus_location_avoids_nesting_inside_raw_pdfs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "corpus" / "raw_pdfs"
            source.mkdir(parents=True)
            self.assertEqual(default_corpus_directory(str(source)), root / "corpus")

    def test_clean_title(self):
        self.assertEqual(clean_title("  A Study on NLP\n\t  "), "A Study on NLP")
        self.assertEqual(clean_title("...Paper Title..."), "Paper Title")

    def test_valid_title(self):
        self.assertTrue(valid_title("Deep Learning for Optical Flow Estimation"))
        self.assertFalse(valid_title("Microsoft Word - Doc1"))
        self.assertFalse(valid_title("https://example.com"))
        self.assertFalse(valid_title("short"))

    def test_slugify(self):
        self.assertEqual(slugify("Deep & Fast Flow: A Study!"), "Deep_and_Fast_Flow_A_Study")
        self.assertEqual(slugify("Paper 2024 (Revised)"), "Paper_2024_Revised")

    def test_title_key(self):
        self.assertEqual(
            title_key("Deep Learning for Flow (Preprint)"),
            "deeplearningforflow",
        )

    def test_extract_year_from_filename(self):
        self.assertEqual(extract_year_from_filename(Path("paper_2023.pdf")), 2023)
        self.assertEqual(extract_year_from_filename(Path("Study (2024) Final.docx")), 2024)
        self.assertIsNone(extract_year_from_filename(Path("no_year_here.pdf")))

    def test_extract_title_html(self):
        with tempfile.NamedTemporaryFile("w", suffix=".html") as tmp:
            tmp.write("<html><head><title>My Scientific Paper Title</title></head><body></body></html>")
            tmp.flush()
            title = extract_title(Path(tmp.name))
            self.assertEqual(title, "My Scientific Paper Title")


if __name__ == "__main__":
    unittest.main()
