"""Unit tests for hashing utilities."""

import tempfile
import unittest
from pathlib import Path

from corpus_converter.hashing import sha256_bytes, sha256_file


class HashingTest(unittest.TestCase):
    def test_sha256_bytes(self):
        digest = sha256_bytes(b"hello world")
        self.assertEqual(digest, "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9")

    def test_sha256_file(self):
        with tempfile.NamedTemporaryFile() as tmp:
            tmp.write(b"hello world")
            tmp.flush()
            digest = sha256_file(Path(tmp.name))
            self.assertEqual(digest, "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9")


if __name__ == "__main__":
    unittest.main()
