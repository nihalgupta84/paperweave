"""Unit tests for JSON and JSONL I/O utilities."""

import tempfile
import unittest
from pathlib import Path

from corpus_converter.io import read_json, read_jsonl, write_json, write_jsonl


class IoTest(unittest.TestCase):
    def test_read_json_missing_file_returns_default(self):
        self.assertEqual(read_json(Path("/nonexistent/file.json"), {"default": 1}), {"default": 1})

    def test_read_json_corrupt_file_returns_default(self):
        with tempfile.NamedTemporaryFile("w") as tmp:
            tmp.write("{corrupt json")
            tmp.flush()
            self.assertIsNone(read_json(Path(tmp.name)))

    def test_write_and_read_json_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "test.json"
            data = {"key": "value", "numbers": [1, 2, 3]}
            write_json(path, data)
            self.assertEqual(read_json(path), data)

    def test_write_and_read_jsonl_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "test.jsonl"
            records = [{"id": 1, "name": "first"}, {"id": 2, "name": "second"}]
            write_jsonl(path, records)
            self.assertEqual(read_jsonl(path), records)


if __name__ == "__main__":
    unittest.main()
