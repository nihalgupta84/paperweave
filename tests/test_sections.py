"""Unit tests for section classification and heading parsing."""

import unittest

from corpus_converter.sections import assign_sections, classify_heading, clean_heading


class SectionsTest(unittest.TestCase):
    def test_clean_heading(self):
        self.assertEqual(clean_heading("1. Introduction"), "Introduction")
        self.assertEqual(clean_heading("IV. EXPERIMENTAL RESULTS"), "EXPERIMENTAL RESULTS")
        self.assertEqual(clean_heading("3.2.1 Proposed Network Architecture"), "Proposed Network Architecture")

    def test_classify_heading(self):
        self.assertEqual(classify_heading("1. Introduction"), "introduction")
        self.assertEqual(classify_heading("2. Related Work"), "related_work")
        self.assertEqual(classify_heading("3. Proposed Methodology"), "methodology")
        self.assertEqual(classify_heading("4. Experiments"), "experiments")
        self.assertEqual(classify_heading("5. Quantitative Results and Ablations"), "results")
        self.assertEqual(classify_heading("6. Discussion and Limitations"), "discussion")
        self.assertEqual(classify_heading("7. Conclusion and Future Work"), "conclusion")
        self.assertEqual(classify_heading("References"), "references")
        self.assertEqual(classify_heading("Random Unrecognized Header"), "unknown")

    def test_assign_sections(self):
        blocks = [
            {"block_id": "b1", "type": "title", "heading_level": 1, "text": "1. Introduction"},
            {"block_id": "b2", "type": "paragraph", "heading_level": None, "text": "This introduces our work."},
            {"block_id": "b3", "type": "title", "heading_level": 1, "text": "2. Methodology"},
            {
                "block_id": "b4",
                "type": "paragraph",
                "heading_level": None,
                "text": "We describe the model architecture.",
            },
        ]
        assigned = assign_sections(blocks)
        self.assertEqual(assigned[0]["section_role"], "introduction")
        self.assertEqual(assigned[1]["section_role"], "introduction")
        self.assertEqual(assigned[2]["section_role"], "methodology")
        self.assertEqual(assigned[3]["section_role"], "methodology")


if __name__ == "__main__":
    unittest.main()
