"""Unit tests for taxonomy term presence and document classification."""

import unittest

from corpus_converter.taxonomy import classify_document, term_present


class TaxonomyTest(unittest.TestCase):
    def test_term_present(self):
        self.assertTrue(term_present("cnn", "We train a deep CNN model."))
        self.assertTrue(term_present("transformer", "A novel vision transformer architecture."))
        self.assertFalse(term_present("cnn", "scnn is not convolutional"))
        self.assertFalse(term_present("mamba", "The venomous snake"))

    def test_classify_document(self):
        taxonomy = {
            "method_family": {
                "method.transformer": ["transformer", "self-attention"],
                "method.cnn": ["cnn", "convolutional neural network"],
            }
        }
        blocks = [
            {
                "document_id": "doc_123",
                "block_id": "blk_456",
                "page_index": 0,
                "section_path": ["Method"],
                "text": "We propose a vision transformer module.",
            }
        ]
        assigned = classify_document(blocks, taxonomy)
        self.assertEqual(len(assigned["method_family"]), 1)
        self.assertEqual(assigned["method_family"][0]["id"], "method.transformer")
        self.assertEqual(assigned["method_family"][0]["evidence"][0]["block_id"], "blk_456")


if __name__ == "__main__":
    unittest.main()
