import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PhaseOnePipelineTest(unittest.TestCase):
    def test_in_corpus_exact_duplicate_is_quarantined_before_processing(self):
        with tempfile.TemporaryDirectory() as temporary:
            corpus = Path(temporary) / "corpus"
            legacy = corpus / "raw_pdfs"
            legacy.mkdir(parents=True)
            content = b"%PDF-same-exact-document"
            (legacy / "paper.pdf").write_bytes(content)
            (legacy / "paper_copy.pdf").write_bytes(content)
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "01_prepare_inputs.py"),
                    "--input",
                    str(legacy),
                    "--corpus-dir",
                    str(corpus),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(len(list((corpus / "pdfs").glob("*.pdf"))), 1)
            self.assertEqual(len(list((corpus / "quarantine" / "duplicates").glob("*.pdf"))), 1)
            duplicates = (corpus / "manifests" / "duplicates.jsonl").read_text()
            self.assertIn('"action": "quarantined"', duplicates)

    def test_ingestion_uses_stable_ids_and_deduplicates_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            corpus = Path(temporary) / "corpus"
            source.mkdir()
            (source / "one.pdf").write_bytes(b"same-document")
            (source / "duplicate.pdf").write_bytes(b"same-document")

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "01_prepare_inputs.py"),
                    "--input",
                    str(source),
                    "--corpus-dir",
                    str(corpus),
                    "--rename-mode",
                    "keep",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            records = [
                json.loads(line)
                for line in (corpus / "manifests" / "documents.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(records), 1)
            self.assertEqual(len(list((corpus / "pdfs").glob("*.pdf"))), 1)
            self.assertRegex(records[0]["document_id"], r"^doc_[0-9a-f]{16}$")
            self.assertEqual(records[0]["canonical_path"], f"pdfs/{records[0]['file_name']}")

    def test_mixed_formats_prefer_pdf_and_skip_unsupported(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            corpus = Path(temporary) / "corpus"
            source.mkdir()
            title = "Unified Study of Research Models"
            (source / "Unified_Study_of_Research_Models.pdf").write_bytes(b"synthetic-pdf")
            (source / "Unified_Study_of_Research_Models.html").write_text(
                f"<html><head><title>{title}</title></head><body><h1>{title}</h1><p>"
                + ("This is substantial scholarly HTML content. " * 20)
                + "</p></body></html>",
                encoding="utf-8",
            )
            with zipfile.ZipFile(source / "Unified_Study_of_Research_Models.docx", "w") as archive:
                archive.writestr(
                    "docProps/core.xml",
                    '<?xml version="1.0"?><cp:coreProperties xmlns:cp="x" xmlns:dc="y">'
                    f"<dc:title>{title}</dc:title></cp:coreProperties>",
                )
                archive.writestr(
                    "word/document.xml",
                    '<?xml version="1.0"?><w:document xmlns:w="x"><w:body>'
                    f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>{title}</w:t></w:r></w:p>'
                    f'<w:p><w:r><w:t>{"DOCX scholarly content. " * 30}</w:t></w:r></w:p>'
                    "</w:body></w:document>",
                )
            (source / "results.csv").write_text("metric,value\naccuracy,0.9\n", encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "01_prepare_inputs.py"),
                    "--input",
                    str(source),
                    "--corpus-dir",
                    str(corpus),
                    "--rename-mode",
                    "title",
                    "--format-policy",
                    "prefer-pdf",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            records = [json.loads(line) for line in (corpus / "manifests" / "documents.jsonl").read_text().splitlines()]
            self.assertEqual(len(records), 3)
            self.assertEqual(len({record["work_id"] for record in records}), 1)
            selected = [record for record in records if record["selected_for_extraction"]]
            self.assertEqual([record["format"] for record in selected], ["pdf"])
            self.assertIn("results.csv", (corpus / "logs" / "skipped_unsupported_files.txt").read_text())

    def test_docx_only_pipeline_and_unavailable_model_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            corpus = Path(temporary) / "corpus"
            source.mkdir()
            title = "DOCX Research Methodology Study"
            paragraphs = [
                ("Heading1", title),
                ("Heading1", "Abstract"),
                (None, "This study investigates a documented research problem using a controlled methodology. " * 8),
                ("Heading1", "Methodology"),
                (
                    None,
                    "The proposed method combines a transformer with supervised learning and careful evaluation. " * 8,
                ),
                ("Heading1", "Experiments"),
                (
                    None,
                    "The experiment reports accuracy of 91.2 percent on the Reddit dataset with an F1-score of 0.90. "
                    * 8,
                ),
            ]
            xml_paragraphs = []
            for style, text_value in paragraphs:
                style_xml = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
                xml_paragraphs.append(f"<w:p>{style_xml}<w:r><w:t>{text_value}</w:t></w:r></w:p>")
            with zipfile.ZipFile(source / "study.docx", "w") as archive:
                archive.writestr(
                    "docProps/core.xml",
                    '<?xml version="1.0"?><cp:coreProperties xmlns:cp="x" xmlns:dc="y">'
                    f"<dc:title>{title}</dc:title></cp:coreProperties>",
                )
                archive.writestr(
                    "word/document.xml",
                    '<?xml version="1.0"?><w:document xmlns:w="x"><w:body>'
                    + "".join(xml_paragraphs)
                    + "</w:body></w:document>",
                )
            (source / "study.html").write_text(
                f"<html><head><title>{title}</title></head><body><h1>{title}</h1><p>Alternate HTML.</p></body></html>",
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "01_prepare_inputs.py"),
                    "--input",
                    str(source),
                    "--corpus-dir",
                    str(corpus),
                    "--format-policy",
                    "prefer-pdf",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "corpus_converter.cli",
                    "postprocess",
                    "--corpus",
                    str(corpus),
                    "--taxonomy-profile",
                    "core",
                    "--semantic-provider",
                    "ollama",
                    "--model",
                    "missing",
                    "--base-url",
                    "http://127.0.0.1:1",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            result = json.loads(completed.stdout)
            self.assertEqual(result["non_pdf_normalization"]["done"], 1)
            self.assertEqual(result["semantic_provider"]["effective"], "deterministic")
            self.assertIn("unavailable", result["semantic_provider"]["fallback_reason"].lower())
            selected = [
                record
                for record in (
                    json.loads(line) for line in (corpus / "manifests" / "documents.jsonl").read_text().splitlines()
                )
                if record["selected_for_extraction"]
            ]
            self.assertEqual(len(selected), 1)
            self.assertEqual(selected[0]["format"], "docx")
            paper_dir = corpus / "papers" / selected[0]["document_id"]
            self.assertTrue((paper_dir / "quality.json").exists())
            self.assertTrue((paper_dir / "sections.jsonl").exists())
            reports = {path.name for path in (corpus / "synthesis").glob("*.md")}
            self.assertTrue(
                {
                    "methodology.md",
                    "experiments.md",
                    "datasets.md",
                    "literature_review.md",
                    "references.md",
                    "all_papers.md",
                }
                <= reports
            )

    def test_flat_document_output_and_page_oriented_blocks(self):
        with tempfile.TemporaryDirectory() as temporary:
            corpus = Path(temporary) / "corpus"
            pdf_dir = corpus / "pdfs"
            auto_dir = corpus / "raw" / "mineru" / "sample" / "auto"
            images_dir = auto_dir / "images"
            manifest_dir = corpus / "manifests"
            pdf_dir.mkdir(parents=True)
            images_dir.mkdir(parents=True)
            manifest_dir.mkdir(parents=True)

            pdf_bytes = b"synthetic-pdf-fixture"
            digest = hashlib.sha256(pdf_bytes).hexdigest()
            document_id = f"doc_{digest[:16]}"
            (pdf_dir / "sample.pdf").write_bytes(pdf_bytes)
            (auto_dir / "sample_origin.pdf").write_bytes(pdf_bytes)
            (images_dir / "figure.png").write_bytes(b"synthetic-image")
            (auto_dir / "sample.md").write_text("# Sample\n\n![Figure](images/figure.png)\n", encoding="utf-8")
            content = {
                "pages": [
                    {
                        "page_idx": 3,
                        "blocks": [
                            {"type": "text", "text": "ABSTRACT", "text_level": 1, "bbox": [1, 1, 3, 2]},
                            {
                                "type": "text",
                                "text": "This paper studies optical flow in fog and proposes a robust RAFT model evaluated on Sintel.",
                                "bbox": [1, 2, 3, 4],
                            },
                            {"type": "text", "text": "3 Methodology", "text_level": 1, "bbox": [1, 5, 3, 6]},
                            {
                                "type": "text",
                                "text": "The proposed method uses a correlation volume and transformer module for efficient optical flow estimation.",
                                "bbox": [1, 7, 3, 8],
                            },
                            {"type": "text", "text": "4 Experiments", "text_level": 1, "bbox": [1, 9, 3, 10]},
                            {
                                "type": "text",
                                "text": "On the Sintel benchmark the method obtains an endpoint error (EPE) of 1.23 and runs at 30 FPS.",
                                "bbox": [1, 11, 3, 12],
                            },
                            {
                                "type": "image",
                                "img_path": "images/figure.png",
                                "image_caption": ["Architecture"],
                                "bbox": [5, 6, 7, 8],
                            },
                        ],
                    }
                ]
            }
            (auto_dir / "sample_content_list_v2.json").write_text(json.dumps(content), encoding="utf-8")
            manifest = {
                "document_id": document_id,
                "work_id": f"work_{digest[:16]}",
                "sha256": digest,
                "file_name": "sample.pdf",
                "pdf_path": "pdfs/sample.pdf",
                "title": "Sample Paper",
                "normalization_status": "pending",
            }
            (manifest_dir / "documents.jsonl").write_text(json.dumps(manifest) + "\n", encoding="utf-8")

            command = [
                sys.executable,
                str(ROOT / "scripts" / "04_format_mineru_output.py"),
                "--corpus-dir",
                str(corpus),
                "--parser-version",
                "test",
            ]
            first = subprocess.run(command, check=True, capture_output=True, text=True)
            second = subprocess.run(command, check=True, capture_output=True, text=True)

            paper_dir = corpus / "papers" / document_id
            self.assertIn("DONE:", first.stdout)
            self.assertIn("SKIP:", second.stdout)
            self.assertTrue((paper_dir / "paper.md").is_file())
            self.assertTrue((paper_dir / "document.json").is_file())
            self.assertTrue((paper_dir / "blocks.jsonl").is_file())
            self.assertFalse((paper_dir / document_id).exists())

            blocks = [
                json.loads(line) for line in (paper_dir / "blocks.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(blocks), 7)
            self.assertTrue(all(block["page_index"] == 3 for block in blocks))
            self.assertTrue(all(block["block_id"].startswith("blk_") for block in blocks))
            self.assertTrue(blocks[-1]["asset_path"].startswith("assets/"))
            self.assertIn("assets/", (paper_dir / "paper.md").read_text(encoding="utf-8"))

            updated_manifest = json.loads((manifest_dir / "documents.jsonl").read_text(encoding="utf-8").strip())
            self.assertEqual(updated_manifest["normalization_status"], "complete")

            postprocess = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "corpus_converter.cli",
                    "postprocess",
                    "--corpus",
                    str(corpus),
                    "--taxonomy-profile",
                    "computer_vision/optical_flow",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            result = json.loads(postprocess.stdout)
            self.assertEqual(result["evidence"]["invalid"], 0)
            self.assertEqual(result["synthesis"]["reports"], 6)
            record_dir = corpus / "records" / f"work_{digest[:16]}"
            self.assertTrue((record_dir / "analysis.json").exists())
            self.assertTrue((record_dir / "experiments.json").exists())
            self.assertTrue((record_dir / "taxonomy.json").exists())
            reports = {path.name for path in (corpus / "synthesis").glob("*.md")}
            self.assertTrue(
                {
                    "methodology.md",
                    "experiments.md",
                    "datasets.md",
                    "literature_review.md",
                    "references.md",
                    "all_papers.md",
                }
                <= reports
            )
            combined = (corpus / "synthesis" / "all_papers.md").read_text(encoding="utf-8")
            self.assertIn(f"../papers/{document_id}/assets/", combined)


if __name__ == "__main__":
    unittest.main()
