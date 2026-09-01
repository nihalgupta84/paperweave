"""Unit tests for gold benchmark evaluation logic."""

import unittest

from corpus_converter.evaluation import prf


class EvaluationTest(unittest.TestCase):
    def test_prf_perfect_match(self):
        predicted = {"ImageNet", "COCO"}
        expected = {"ImageNet", "COCO"}
        scores = prf(predicted, expected)
        self.assertEqual(scores, {"precision": 1.0, "recall": 1.0, "f1": 1.0})

    def test_prf_partial_match(self):
        predicted = {"ImageNet", "MNIST"}
        expected = {"ImageNet", "COCO"}
        scores = prf(predicted, expected)
        self.assertEqual(scores["precision"], 0.5)
        self.assertEqual(scores["recall"], 0.5)
        self.assertEqual(scores["f1"], 0.5)

    def test_prf_empty_predictions_and_expected(self):
        scores = prf(set(), set())
        self.assertEqual(scores, {"precision": 1.0, "recall": 1.0, "f1": 1.0})

    def test_prf_empty_predictions_with_expected(self):
        scores = prf(set(), {"ImageNet"})
        self.assertEqual(scores, {"precision": 0.0, "recall": 0.0, "f1": 0.0})


if __name__ == "__main__":
    unittest.main()
