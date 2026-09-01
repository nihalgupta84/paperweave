"""Regression tests for release-blocking safety and correctness invariants."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from corpus_converter import __version__
from corpus_converter.citation_graph import build_citation_graph
from corpus_converter.ingestion import ingest, title_key, work_candidates
from corpus_converter.io import read_json, read_jsonl, write_json, write_jsonl
from corpus_converter.merge import auto_merge_candidates
from corpus_converter.review import review_corpus
from corpus_converter.semantic import analyze_document, enrich_document, validate_evidence
from corpus_converter.synthesis import synthesize_incremental
from corpus_converter.validation import RecordValidationError, validate_analysis

ROOT = Path(__file__).resolve().parents[1]


class HardeningRegressionTest(unittest.TestCase):
    def test_source_version_matches_package_metadata(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(f'version = "{__version__}"', pyproject)
        citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
        self.assertIn(f"version: {__version__}", citation)

    def test_incremental_single_file_ingestion_preserves_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            corpus = root / "corpus"
            first = root / "first.html"
            second = root / "second.html"
            first.write_text("<title>First Independent Research Paper</title>", encoding="utf-8")
            second.write_text("<title>Second Independent Research Paper</title>", encoding="utf-8")

            ingest(first, corpus)
            ingest(second, corpus)

            records = read_jsonl(corpus / "manifests" / "documents.jsonl")
            self.assertEqual(len(records), 2)
            self.assertEqual(
                {record["title"] for record in records},
                {
                    "First Independent Research Paper",
                    "Second Independent Research Paper",
                },
            )

    def test_conflicting_dois_prevent_same_title_work_grouping(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            title = "A Shared but Non-Unique Scientific Paper Title"
            (source / "first.html").write_text(
                f"<title>{title}</title><p>DOI: 10.1000/first-paper</p>", encoding="utf-8"
            )
            (source / "second.html").write_text(
                f"<title>{title}</title><p>DOI: 10.1000/second-paper</p>", encoding="utf-8"
            )
            corpus = root / "corpus"
            ingest(source, corpus)
            records = read_jsonl(corpus / "manifests" / "documents.jsonl")
            self.assertEqual(len({record["work_id"] for record in records}), 2)

    def test_trigram_blocking_retains_typo_candidate(self):
        left = "Deep Learning Methods for Optical Flow in Adverse Weather Conditions"
        right = "Deap Learning Methods for Optical Flow in Adverse Weather Conditions"
        records = [
            {
                "document_id": f"doc_{index:016x}",
                "work_id": f"work_{index:016x}",
                "title": f"Unique Topic Number {index} With A Different Research Subject",
                "title_key": title_key(f"Unique Topic Number {index} With A Different Research Subject"),
            }
            for index in range(61)
        ]
        records.extend(
            [
                {
                    "document_id": "doc_aaaaaaaaaaaaaaaa",
                    "work_id": "work_aaaaaaaaaaaaaaaa",
                    "title": left,
                    "title_key": title_key(left),
                },
                {
                    "document_id": "doc_bbbbbbbbbbbbbbbb",
                    "work_id": "work_bbbbbbbbbbbbbbbb",
                    "title": right,
                    "title_key": title_key(right),
                },
            ]
        )
        candidates = work_candidates(records)
        self.assertTrue(
            any(
                {candidate["left_document_id"], candidate["right_document_id"]}
                == {"doc_aaaaaaaaaaaaaaaa", "doc_bbbbbbbbbbbbbbbb"}
                for candidate in candidates
            )
        )

    def test_auto_merge_requires_strong_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            corpus = Path(temporary)
            left_doc = "doc_0000000000000001"
            right_doc = "doc_0000000000000002"
            left_work = "work_0000000000000001"
            right_work = "work_0000000000000002"
            for work_id, doc_id, title in (
                (left_work, left_doc, "Deep Learning for Optical Flow Part I"),
                (right_work, right_doc, "Deep Learning for Optical Flow Part II"),
            ):
                record_dir = corpus / "records" / work_id / "documents" / doc_id
                record_dir.mkdir(parents=True)
                write_json(
                    record_dir.parents[1] / "work.json",
                    {
                        "work_id": work_id,
                        "title": title,
                        "document_ids": [doc_id],
                        "doi": None,
                        "arxiv_id": None,
                    },
                )
            write_jsonl(
                corpus / "manifests" / "documents.jsonl",
                [
                    {"document_id": left_doc, "work_id": left_work},
                    {"document_id": right_doc, "work_id": right_work},
                ],
            )
            write_jsonl(
                corpus / "manifests" / "work_match_candidates.jsonl",
                [
                    {
                        "left_document_id": left_doc,
                        "right_document_id": right_doc,
                        "similarity": 0.9841,
                        "status": "review_needed",
                    }
                ],
            )

            result = auto_merge_candidates(corpus)

            self.assertEqual(result["merged_count"], 0)
            self.assertEqual(result["blocked_without_strong_identity"], 1)
            self.assertTrue((corpus / "records" / right_work).exists())

    def test_auto_merge_accepts_matching_doi_and_keeps_backups(self):
        with tempfile.TemporaryDirectory() as temporary:
            corpus = Path(temporary)
            left_doc = "doc_0000000000000001"
            right_doc = "doc_0000000000000002"
            left_work = "work_0000000000000001"
            right_work = "work_0000000000000002"
            for work_id, doc_id, title in (
                (left_work, left_doc, "A Study of Reliable Optical Flow"),
                (right_work, right_doc, "A Study of Reliable Optical Flow Revised"),
            ):
                document_dir = corpus / "records" / work_id / "documents" / doc_id
                document_dir.mkdir(parents=True)
                write_json(
                    document_dir.parents[1] / "work.json",
                    {
                        "schema_version": "1.0",
                        "work_id": work_id,
                        "title": title,
                        "authors": [],
                        "year": None,
                        "document_ids": [doc_id],
                        "doi": "10.1000/same-work",
                        "arxiv_id": None,
                        "merge_status": "unreviewed",
                    },
                )
            write_jsonl(
                corpus / "manifests" / "documents.jsonl",
                [
                    {"document_id": left_doc, "work_id": left_work},
                    {"document_id": right_doc, "work_id": right_work},
                ],
            )
            write_jsonl(
                corpus / "manifests" / "work_match_candidates.jsonl",
                [
                    {
                        "left_document_id": left_doc,
                        "right_document_id": right_doc,
                        "similarity": 0.97,
                        "status": "review_needed",
                    }
                ],
            )

            result = auto_merge_candidates(corpus)

            self.assertEqual(result["merged_count"], 1)
            self.assertFalse((corpus / "records" / right_work).exists())
            self.assertEqual(len(list((corpus / "quarantine" / "merged_works").glob("*/secondary_before"))), 1)

    def test_mineru_formatter_preserves_manifest_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            corpus = Path(temporary) / "corpus"
            auto = corpus / "raw" / "mineru" / "sample" / "auto"
            auto.mkdir(parents=True)
            pdf_bytes = b"%PDF-synthetic"
            digest = hashlib.sha256(pdf_bytes).hexdigest()
            document_id = f"doc_{digest[:16]}"
            (auto / "sample_origin.pdf").write_bytes(pdf_bytes)
            (auto / "sample.md").write_text("# A Proper Scientific Paper Title", encoding="utf-8")
            (auto / "sample_content_list.json").write_text(
                json.dumps(
                    [
                        {
                            "type": "text",
                            "text": "A substantive abstract block containing enough content for normalization and analysis.",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            write_jsonl(
                corpus / "manifests" / "documents.jsonl",
                [
                    {
                        "document_id": document_id,
                        "work_id": "work_aaaaaaaaaaaaaaaa",
                        "sha256": digest,
                        "title": "A Proper Scientific Paper Title",
                        "authors": ["Ada Researcher"],
                        "year": 2024,
                        "file_name": "sample.pdf",
                        "canonical_path": "pdfs/sample.pdf",
                        "selected_for_extraction": True,
                        "format": "pdf",
                    }
                ],
            )

            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "04_format_mineru_output.py"), "--corpus-dir", str(corpus)],
                check=True,
                capture_output=True,
                text=True,
            )
            document = json.loads((corpus / "papers" / document_id / "document.json").read_text())
            self.assertEqual(document["authors"], ["Ada Researcher"])
            self.assertEqual(document["year"], 2024)

    def test_schema_validation_raises(self):
        with self.assertRaises(RecordValidationError):
            validate_analysis({})

    def test_synthesis_detects_content_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            corpus = Path(temporary)
            record_dir = corpus / "records" / "work_aaaaaaaaaaaaaaaa"
            record_dir.mkdir(parents=True)
            write_json(
                record_dir / "work.json",
                {
                    "work_id": "work_aaaaaaaaaaaaaaaa",
                    "title": "Before",
                    "document_ids": [],
                },
            )
            synthesize_incremental(corpus)
            write_json(
                record_dir / "work.json",
                {
                    "work_id": "work_aaaaaaaaaaaaaaaa",
                    "title": "After",
                    "document_ids": [],
                },
            )

            result = synthesize_incremental(corpus)

            self.assertEqual(result["regenerated"], 1)
            report = (corpus / "synthesis" / "methodology.md").read_text()
            self.assertIn("After", report)
            self.assertNotIn("Before", report)

    def test_synthesis_creates_reports_for_fresh_empty_corpus(self):
        with tempfile.TemporaryDirectory() as temporary:
            corpus = Path(temporary)
            result = synthesize_incremental(corpus)
            self.assertEqual(result["reports"], 6)
            self.assertTrue((corpus / "synthesis" / "all_papers.md").is_file())

    def test_citation_graph_creates_output_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            corpus = Path(temporary)
            record_dir = corpus / "records" / "work_aaaaaaaaaaaaaaaa"
            record_dir.mkdir(parents=True)
            write_json(
                record_dir / "work.json",
                {
                    "work_id": "work_aaaaaaaaaaaaaaaa",
                    "title": "Only Work",
                    "document_ids": [],
                },
            )
            result = build_citation_graph(corpus)
            self.assertEqual(result["nodes"], 1)
            self.assertTrue((corpus / "synthesis" / "citation_graph.md").exists())

    def test_interactive_review_persists_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            corpus = Path(temporary)
            write_jsonl(
                corpus / "manifests" / "work_match_candidates.jsonl",
                [
                    {
                        "left_document_id": "doc_0000000000000001",
                        "right_document_id": "doc_0000000000000002",
                        "left_title": "Paper One",
                        "right_title": "Paper Two",
                        "similarity": 0.96,
                        "status": "review_needed",
                    }
                ],
            )
            result = review_corpus(corpus, interactive=True, input_fn=lambda _: "r")
            stored = read_jsonl(corpus / "manifests" / "work_match_candidates.jsonl")
            self.assertTrue(result["interactive_completed"])
            self.assertEqual(result["rejected"], 1)
            self.assertEqual(stored[0]["status"], "rejected")

    def test_evidence_validation_checks_coordinates(self):
        with tempfile.TemporaryDirectory() as temporary:
            corpus = Path(temporary)
            document_id = "doc_aaaaaaaaaaaaaaaa"
            write_jsonl(
                corpus / "papers" / document_id / "sections.jsonl",
                [
                    {
                        "document_id": document_id,
                        "block_id": "blk_aaaaaaaaaaaaaaaaaaaa",
                        "page_index": 2,
                        "section_path": ["Methods"],
                    }
                ],
            )
            write_json(
                corpus / "records" / "work_aaaaaaaaaaaaaaaa" / "analysis.json",
                {
                    "evidence": [
                        {
                            "document_id": document_id,
                            "block_id": "blk_aaaaaaaaaaaaaaaaaaaa",
                            "page_index": 9,
                            "section": "Methods",
                        }
                    ]
                },
            )
            self.assertEqual(validate_evidence(corpus)["invalid"], 1)

    def test_model_statements_are_not_marked_semantically_verified(self):
        class Provider:
            def generate_json(self, prompt, schema):
                del prompt, schema
                return {
                    "contributions": [
                        {
                            "statement": "A model-generated claim",
                            "evidence_block_ids": ["blk_aaaaaaaaaaaaaaaaaaaa"],
                        }
                    ],
                    "method_components": [],
                    "training_objectives": [],
                    "limitations": [],
                    "datasets": [],
                    "metrics": [],
                    "results": [],
                }

        with tempfile.TemporaryDirectory() as temporary:
            corpus = Path(temporary)
            document_id = "doc_aaaaaaaaaaaaaaaa"
            work_id = "work_aaaaaaaaaaaaaaaa"
            paper_dir = corpus / "papers" / document_id
            write_json(
                paper_dir / "document.json",
                {
                    "document_id": document_id,
                    "work_id": work_id,
                    "sha256": "a" * 64,
                    "format": "html",
                    "version": "unknown",
                    "title": "A Grounding Test Paper",
                    "authors": [],
                    "year": None,
                    "doi": None,
                    "arxiv_id": None,
                    "source_path": "sources/html/test.html",
                    "parser": {},
                    "block_count": 1,
                    "asset_count": 0,
                },
            )
            write_jsonl(
                paper_dir / "sections.jsonl",
                [
                    {
                        "document_id": document_id,
                        "block_id": "blk_aaaaaaaaaaaaaaaaaaaa",
                        "type": "paragraph",
                        "heading_level": None,
                        "page_index": None,
                        "section_path": ["Methodology"],
                        "section_role": "methodology",
                        "text": "This methodology description is sufficiently long to be selected as substantive source evidence. "
                        * 2,
                        "bbox": None,
                        "asset_path": None,
                        "source": {
                            "parser": "html",
                            "parser_version": "stdlib",
                            "source_file": None,
                            "source_index": 0,
                        },
                    }
                ],
            )
            self.assertTrue(analyze_document(paper_dir, corpus))
            ok, error = enrich_document(paper_dir, corpus, Provider())
            self.assertTrue(ok, error)
            analysis = read_json(corpus / "records" / work_id / "documents" / document_id / "analysis.json", {})
            self.assertEqual(analysis["contributions"][0]["support_status"], "evidence_cited_unverified")


if __name__ == "__main__":
    unittest.main()
