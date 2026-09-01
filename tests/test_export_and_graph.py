"""Unit tests for references, export formats, citation graph, and work merging."""

import tempfile
import unittest
from pathlib import Path

from corpus_converter.citation_graph import build_citation_graph
from corpus_converter.export import export_bibtex, export_csv, export_jsonld
from corpus_converter.io import read_json, write_json, write_jsonl
from corpus_converter.merge import merge_works
from corpus_converter.references import extract_references_from_blocks


class ExportAndGraphTest(unittest.TestCase):
    def test_extract_references_from_blocks(self):
        blocks = [
            {
                "document_id": "doc_1",
                "block_id": "blk_ref1",
                "page_index": 5,
                "section_role": "references",
                "section_path": ["References"],
                "text": "[1] J. Smith and A. Doe, 'Deep Transformers for Vision', IEEE TPAMI, 2023.\n[2] B. Johnson, 'Optical Flow in Fog', CVPR, 2024.",
            }
        ]
        refs = extract_references_from_blocks(blocks)
        self.assertEqual(len(refs), 2)
        self.assertEqual(refs[0]["parsed_year"], 2023)
        self.assertEqual(refs[1]["parsed_year"], 2024)

    def test_exports(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            corpus = Path(tmp_dir) / "corpus"
            records_dir = corpus / "records" / "work_12345"
            records_dir.mkdir(parents=True)

            work = {
                "schema_version": "1.0",
                "work_id": "work_12345",
                "title": "Study on Transformers",
                "authors": ["Jane Doe", "John Smith"],
                "year": 2024,
                "doi": "10.1000/182",
                "document_ids": ["doc_12345"],
            }
            write_json(records_dir / "work.json", work)
            write_json(records_dir / "experiments.json", {"datasets": [{"name": "COCO"}], "metrics": [{"name": "F1"}]})
            write_json(records_dir / "taxonomy.json", {"facets": {"method_family": [{"name": "Transformer"}]}})

            bib_file = corpus / "exports" / "corpus.bib"
            csv_file = corpus / "exports" / "corpus.csv"
            jsonld_file = corpus / "exports" / "corpus.jsonld"

            res_bib = export_bibtex(corpus, bib_file)
            self.assertEqual(res_bib["exported"], 1)
            self.assertTrue(bib_file.is_file())
            self.assertIn("@article", bib_file.read_text(encoding="utf-8"))

            res_csv = export_csv(corpus, csv_file)
            self.assertEqual(res_csv["exported"], 1)
            self.assertTrue(csv_file.is_file())
            self.assertIn("Study on Transformers", csv_file.read_text(encoding="utf-8"))

            res_jsonld = export_jsonld(corpus, jsonld_file)
            self.assertEqual(res_jsonld["exported"], 1)
            self.assertTrue(jsonld_file.is_file())
            self.assertIn("ScholarlyArticle", jsonld_file.read_text(encoding="utf-8"))

    def test_citation_graph_and_merge(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            corpus = Path(tmp_dir) / "corpus"
            work_1 = "work_0000000000000001"
            work_2 = "work_0000000000000002"
            doc_1 = "doc_0000000000000001"
            doc_2 = "doc_0000000000000002"
            rec1 = corpus / "records" / work_1
            rec2 = corpus / "records" / work_2
            rec1.mkdir(parents=True)
            rec2.mkdir(parents=True)

            write_json(
                rec1 / "work.json",
                {
                    "schema_version": "1.0",
                    "work_id": work_1,
                    "title": "First Paper on RAFT",
                    "authors": [],
                    "year": None,
                    "doi": None,
                    "arxiv_id": None,
                    "document_ids": [doc_1],
                    "merge_status": "unreviewed",
                },
            )
            write_json(
                rec2 / "work.json",
                {
                    "schema_version": "1.0",
                    "work_id": work_2,
                    "title": "Second Paper Citing RAFT",
                    "authors": [],
                    "year": None,
                    "doi": None,
                    "arxiv_id": None,
                    "document_ids": [doc_2],
                    "merge_status": "unreviewed",
                },
            )
            write_json(
                rec2 / "references.json",
                {
                    "work_id": work_2,
                    "references": [
                        {
                            "raw": "First Paper on RAFT, 2023.",
                            "parsed_title": "First Paper on RAFT",
                            "parsed_year": 2023,
                        }
                    ],
                },
            )
            (corpus / "synthesis").mkdir(parents=True)

            res = build_citation_graph(corpus)
            self.assertEqual(res["nodes"], 2)
            self.assertEqual(res["edges"], 1)
            self.assertTrue((corpus / "records" / "citation_graph.json").is_file())
            self.assertTrue((corpus / "synthesis" / "citation_graph.md").is_file())

            # Test merging work_2 into work_1
            (corpus / "manifests").mkdir(parents=True, exist_ok=True)
            write_jsonl(
                corpus / "manifests" / "documents.jsonl",
                [{"document_id": doc_1, "work_id": work_1}, {"document_id": doc_2, "work_id": work_2}],
            )
            (rec1 / "documents" / doc_1).mkdir(parents=True)
            (rec2 / "documents" / doc_2).mkdir(parents=True)
            write_json(
                corpus / "papers" / doc_2 / "document.json",
                {
                    "document_id": doc_2,
                    "work_id": work_2,
                    "sha256": "2" * 64,
                    "format": "pdf",
                    "version": "unknown",
                    "title": "Second Paper Citing RAFT",
                    "authors": [],
                    "year": None,
                    "doi": None,
                    "arxiv_id": None,
                    "source_path": "pdfs/second.pdf",
                    "parser": {},
                    "block_count": 0,
                    "asset_count": 0,
                },
            )

            ok = merge_works(corpus, work_1, work_2)
            self.assertTrue(ok)
            merged_work = rec1 / "work.json"
            self.assertTrue(merged_work.is_file())
            self.assertFalse(rec2.exists())
            backups = list((corpus / "quarantine" / "merged_works").glob("*/secondary_before"))
            self.assertEqual(len(backups), 1)
            updated_document = read_json(corpus / "papers" / doc_2 / "document.json", {})
            self.assertEqual(updated_document["work_id"], work_1)


if __name__ == "__main__":
    unittest.main()
