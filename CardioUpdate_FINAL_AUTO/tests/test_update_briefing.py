import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import update_briefing as briefing


class BriefingReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.pool = [{
            "pmid": "123",
            "title": "Recent preventive cardiology study",
            "journalTitle": "Journal",
            "source_database": "PubMed",
        }]

    def test_invalid_ai_items_are_rejected(self):
        data = {"items": [{"source_n": 99, "title": "Invented"}]}
        self.assertEqual(briefing.parsed_ai_items(data, self.pool), [])
        self.assertEqual(briefing.parsed_ai_items({"items": [{"source_n": -1}]}, self.pool), [])
        self.assertEqual(briefing.parsed_ai_items([], self.pool), [])

    def test_fallback_keeps_verified_source_link(self):
        items = briefing.fallback_items(self.pool)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], "https://pubmed.ncbi.nlm.nih.gov/123/")
        self.assertIn("vigilancia bibliográfica", items[0]["what_happened"])


if __name__ == "__main__":
    unittest.main()
