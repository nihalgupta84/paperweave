"""Tests for GROBID, local retrieval, and related-paper knowledge graphs."""

from __future__ import annotations

import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch
from xml.etree import ElementTree

from corpus_converter.citation_graph import build_knowledge_graph
from corpus_converter.grobid import GrobidAdapter, enrich_corpus_with_grobid, parse_tei
from corpus_converter.ingestion import pdf_preflight
from corpus_converter.io import read_json, write_json, write_jsonl
from corpus_converter.pipeline import prune_mineru_output, run_mineru, run_pipeline
from corpus_converter.providers import resolve_provider
from corpus_converter.retrieval import build_search_index, search_corpus
from corpus_converter.semantic import discover_dataset_mentions, find_mentions

TEI = b"""<?xml version="1.0"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader><fileDesc><titleStmt>
<title>Reliable Flow</title><author><persName><forename>Ada</forename><surname>Lovelace</surname></persName></author>
</titleStmt><publicationStmt><date when="2024"/><idno type="DOI">10.1234/example</idno></publicationStmt>
<sourceDesc><bibl/></sourceDesc></fileDesc></teiHeader><text><back><listBibl><biblStruct>
<analytic><title>Earlier Flow</title><author><persName><forename>Grace</forename><surname>Hopper</surname></persName></author></analytic>
<monogr><imprint><date when="2020"/></imprint></monogr><idno type="DOI">10.1234/earlier</idno>
</biblStruct></listBibl></back></text></TEI>"""


def make_document(corpus: Path, suffix: str, title: str, text: str, dataset: str = "KITTI") -> tuple[str, str]:
    document_id = f"doc_{suffix * 16}"
    work_id = f"work_{suffix * 16}"
    paper = corpus / "papers" / document_id
    record = corpus / "records" / work_id
    write_json(
        paper / "document.json",
        {
            "document_id": document_id,
            "work_id": work_id,
            "sha256": suffix * 64,
            "format": "pdf",
            "version": "unknown",
            "title": title,
            "authors": [],
            "year": None,
            "doi": None,
            "arxiv_id": None,
            "source_path": None,
            "parser": {"name": "test"},
            "block_count": 1,
            "asset_count": 0,
        },
    )
    write_jsonl(
        paper / "sections.jsonl",
        [
            {
                "block_id": f"blk_{suffix * 16}",
                "document_id": document_id,
                "type": "paragraph",
                "heading_level": None,
                "page_index": 1,
                "section_path": ["Method"],
                "section_role": "methodology",
                "text": text,
                "bbox": None,
                "asset_path": None,
                "source": {"parser": "test", "parser_version": None, "source_file": None, "source_index": 0},
            }
        ],
    )
    write_json(
        record / "work.json",
        {
            "schema_version": "1.0",
            "work_id": work_id,
            "title": title,
            "authors": [],
            "year": None,
            "doi": None,
            "arxiv_id": None,
            "document_ids": [document_id],
            "merge_status": "unreviewed",
        },
    )
    write_json(record / "analysis.json", {"methodology": [{"statement": text}]})
    write_json(record / "experiments.json", {"datasets": [{"name": dataset}]})
    write_json(
        record / "taxonomy.json",
        {"facets": {"task": [{"id": "task.optical_flow", "name": "Optical flow"}]}},
    )
    return document_id, work_id


class IntegrationTests(unittest.TestCase):
    def test_parser_cleanup_removes_only_completed_generated_document(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            corpus = Path(temporary)
            document_id = "doc_" + "a" * 16
            raw = corpus / "raw" / "mineru" / "paper" / "auto"
            raw.mkdir(parents=True)
            (raw / "paper.md").write_text("paper", encoding="utf-8")
            paper = corpus / "papers" / document_id
            paper.mkdir(parents=True)
            (paper / ".done").write_text("done\n", encoding="utf-8")
            write_json(paper / "document.json", {"parser": {"raw_directory": str(raw)}})
            write_jsonl(
                corpus / "manifests" / "documents.jsonl",
                [
                    {
                        "document_id": document_id,
                        "stages": {"mineru": {"status": "complete", "raw_directory": str(raw.parent)}},
                    }
                ],
            )
            result = prune_mineru_output(corpus, [document_id])
            self.assertEqual(result["removed_document_folders"], 1)
            self.assertFalse(raw.parent.exists())
            self.assertFalse(read_json(paper / "document.json")["parser"]["raw_retained"])

    def test_auto_provider_uses_llm_checker_ranked_installed_model(self) -> None:
        checker_output = '{"models":[{"name":"small:latest","score":40},{"name":"qwen:7b","score":92}]}'
        with (
            patch("corpus_converter.providers.shutil.which", return_value="/usr/bin/llm-checker"),
            patch(
                "corpus_converter.providers.request_json",
                side_effect=[
                    {"models": [{"name": "qwen:7b"}, {"name": "small:latest"}]},
                    {"models": [{"name": "qwen:7b"}]},
                ],
            ),
            patch(
                "corpus_converter.providers.subprocess.run",
                return_value=CompletedProcess([], 0, checker_output, ""),
            ),
        ):
            resolution = resolve_provider("auto", None, None)
        self.assertEqual(resolution.effective, "ollama")
        self.assertEqual(resolution.model, "qwen:7b")

    def test_discovers_unlisted_datasets_without_metric_substring_false_positives(self) -> None:
        blocks = [
            {
                "document_id": "doc_" + "a" * 16,
                "block_id": "blk_" + "b" * 20,
                "page_index": 2,
                "section_path": ["Experiments"],
                "section_role": "experiments",
                "type": "text",
                "text": (
                    "We evaluate on the CARE and TeddyCup datasets and report Dice. Feature maps are compared. "
                    "A public dataset like TotalSegmentator<sup>58</sup> is also evaluated."
                ),
            },
            {
                "document_id": "doc_" + "a" * 16,
                "block_id": "blk_" + "c" * 20,
                "page_index": 3,
                "section_path": ["References"],
                "section_role": "references",
                "type": "text",
                "text": "A cited optical-flow paper reports EPE on KITTI.",
            },
        ]
        datasets = {item["name"] for item in discover_dataset_mentions(blocks, ())}
        metrics = {item["name"] for item in find_mentions(blocks[:1], ("Dice", "mAP", "EPE"))}
        self.assertEqual(datasets, {"CARE", "TeddyCup", "TotalSegmentator"})
        self.assertEqual(metrics, {"Dice"})

    def test_discovers_dataset_with_title_case_suffix(self) -> None:
        blocks = [
            {
                "document_id": "doc_" + "a" * 16,
                "block_id": "blk_" + "b" * 20,
                "page_index": 2,
                "section_path": ["Experiments"],
                "section_role": "experiments",
                "type": "text",
                "text": "Experiments use the CARE Dataset and report a Dice score.",
            }
        ]

        datasets = {item["name"] for item in discover_dataset_mentions(blocks, ())}

        self.assertEqual(datasets, {"CARE"})

    def test_package_native_run_completes_html_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "papers"
            corpus = root / "corpus"
            source.mkdir()
            (source / "study.html").write_text(
                "<html><head><title>Underwater Image Enhancement Study</title></head><body>"
                "<h1>Underwater Image Enhancement Study</h1><h2>Methodology</h2>"
                f"<p>{'The proposed method improves underwater images using supervised learning. ' * 12}</p>"
                "<h2>Experiments</h2>"
                f"<p>{'Experiments on the UIEB dataset report PSNR and SSIM measurements. ' * 12}</p>"
                "</body></html>",
                encoding="utf-8",
            )
            result = run_pipeline(str(source), corpus)
            self.assertEqual(result["mineru"]["status"], "not_needed")
            self.assertEqual(result["postprocess"]["evidence"]["invalid"], 0)
            self.assertTrue((corpus / "synthesis" / "methodology.md").is_file())
            self.assertTrue((corpus / "synthesis" / "all_papers.md").is_file())

    def test_package_native_run_explains_missing_mineru(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            corpus = Path(temporary)
            pdf = corpus / "pdfs" / "paper.pdf"
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b"%PDF-test")
            write_jsonl(
                corpus / "manifests" / "documents.jsonl",
                [
                    {
                        "document_id": "doc_aaaaaaaaaaaaaaaa",
                        "work_id": "work_aaaaaaaaaaaaaaaa",
                        "sha256": "a" * 64,
                        "format": "pdf",
                        "canonical_path": "pdfs/paper.pdf",
                        "selected_for_extraction": True,
                    }
                ],
            )
            with (
                patch("corpus_converter.pipeline.shutil.which", return_value=None),
                self.assertRaisesRegex(RuntimeError, r"paperweave\[full\]"),
            ):
                run_mineru(corpus)

    def test_grobid_http_client_sends_pdf_and_parses_response(self) -> None:
        requests: list[bytes] = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"true")

            def do_POST(self):  # noqa: N802
                requests.append(self.rfile.read(int(self.headers["Content-Length"])))
                self.send_response(200)
                self.send_header("Content-Type", "application/xml")
                self.end_headers()
                self.wfile.write(TEI)

            def log_message(self, *_args):
                return None

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                pdf = Path(temporary) / "paper.pdf"
                pdf.write_bytes(b"%PDF-test")
                adapter = GrobidAdapter(f"http://127.0.0.1:{server.server_port}")
                self.assertEqual(adapter.probe(), (True, None))
                _xml, metadata = adapter.extract_fulltext(pdf)
            self.assertIn(b"%PDF-test", requests[0])
            self.assertEqual(metadata["doi"], "10.1234/example")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_pdf_preflight_uses_available_pymupdf_import(self) -> None:
        class FakeDocument:
            needs_pass = False

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def __len__(self):
                return 3

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "paper.pdf"
            path.write_bytes(b"%PDF-test")
            with patch("corpus_converter.ingestion._open_pdf", return_value=FakeDocument()):
                self.assertEqual(pdf_preflight(path), {"status": "accepted", "page_count": 3})

    def test_parse_grobid_tei(self) -> None:
        metadata = parse_tei(TEI)
        self.assertEqual(metadata["title"], "Reliable Flow")
        self.assertEqual(metadata["authors"], ["Ada Lovelace"])
        self.assertEqual(metadata["year"], 2024)
        self.assertEqual(metadata["doi"], "10.1234/example")
        self.assertEqual(metadata["references"][0]["parsed_title"], "Earlier Flow")

    def test_grobid_enrichment_fills_missing_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            corpus = Path(temporary)
            document_id, work_id = make_document(corpus, "a", "Reliable Flow", "Optical flow method")
            pdf = corpus / "pdfs" / "paper.pdf"
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b"%PDF-test")
            write_jsonl(
                corpus / "manifests" / "documents.jsonl",
                [{"document_id": document_id, "work_id": work_id, "format": "pdf", "canonical_path": "pdfs/paper.pdf"}],
            )
            with (
                patch("corpus_converter.grobid.GrobidAdapter.probe", return_value=(True, None)),
                patch("corpus_converter.grobid.GrobidAdapter.extract_fulltext", return_value=(TEI, parse_tei(TEI))),
            ):
                result = enrich_corpus_with_grobid(corpus)
            self.assertEqual(result["processed"], 1)
            work = read_json(corpus / "records" / work_id / "work.json")
            self.assertEqual(work["doi"], "10.1234/example")
            self.assertTrue((corpus / "raw" / "grobid" / document_id / "fulltext.tei.xml").is_file())

    def test_local_hybrid_and_vector_search(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            corpus = Path(temporary)
            make_document(corpus, "a", "Night Flow", "Robust optical flow for dark nighttime driving")
            make_document(corpus, "b", "Language Model", "Token prediction for language generation", "WikiText")
            indexed = build_search_index(corpus)
            self.assertEqual(indexed["blocks"], 2)
            hybrid = search_corpus(corpus, "nighttime optical flow", mode="hybrid")
            vector = search_corpus(corpus, "dark flow", mode="vector")
            self.assertEqual(hybrid["results"][0]["title"], "Night Flow")
            self.assertEqual(vector["results"][0]["title"], "Night Flow")

    def test_related_and_heterogeneous_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            corpus = Path(temporary)
            make_document(corpus, "a", "Night Flow", "robust optical flow for nighttime driving")
            make_document(corpus, "b", "Fog Flow", "robust optical flow for foggy driving")
            summary = build_knowledge_graph(corpus)
            self.assertGreaterEqual(summary["related_paper_links"], 1)
            graph = read_json(corpus / "records" / "knowledge_graph.json")
            self.assertTrue(any(node["type"] == "dataset" for node in graph["nodes"]))
            self.assertTrue(any(edge["type"] == "classified_as" for edge in graph["edges"]))
            ElementTree.parse(corpus / "records" / "knowledge_graph.graphml")


if __name__ == "__main__":
    unittest.main()
