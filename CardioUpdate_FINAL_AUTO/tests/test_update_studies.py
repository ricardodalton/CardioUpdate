import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import update_studies as weekly


class WeeklyCandidatePipelineTests(unittest.TestCase):
    def test_build_study_keeps_source_abstracts_without_network_analysis(self):
        article = {
            "pmid": "123", "title": "Randomized heart failure trial",
            "abstractText": "Original source abstract with clinical results.",
            "journalTitle": "Clinical Journal", "firstPublicationDate": "2026-11-13",
            "pubTypeList": {"pubType": ["Randomized Controlled Trial"]},
        }
        translated = [["Resumen", "Traducción local del abstract."]]
        with patch.object(weekly, "structured_abstract_es", return_value=translated), patch.object(weekly.requests, "get", side_effect=AssertionError("No per-article network synthesis is permitted")):
            study = weekly.build_study(article, 20)
        self.assertEqual(study["abstract_en"], article["abstractText"])
        self.assertEqual(study["abstract_es"], translated)
        self.assertEqual(study["url"], "https://pubmed.ncbi.nlm.nih.gov/123/")
        self.assertFalse(weekly.INDIVIDUAL_ANALYSIS_FIELDS.intersection(study))

    def test_existing_analyses_are_removed_without_changing_identity_or_abstracts(self):
        study = {"id": "kept", "title": "Source title", "abstract_en": "Source abstract",
                 "abstract_es": [["Resumen", "Traducción local"]], "url": "https://doi.org/example"}
        stored = dict(study, **{key: "retired" for key in weekly.INDIVIDUAL_ANALYSIS_FIELDS})
        self.assertEqual(weekly.without_individual_analysis(stored), study)
        self.assertIn("analysis_es", stored)

    def test_collection_window_is_saturday_through_friday(self):
        self.assertEqual(
            weekly.collection_window(date(2026, 9, 26)),
            (date(2026, 9, 26), date(2026, 10, 2)),
        )
        self.assertEqual(
            weekly.collection_window(date(2026, 10, 2)),
            (date(2026, 9, 26), date(2026, 10, 2)),
        )

    def test_newly_detected_old_publication_enters_current_cycle(self):
        item = {
            "pmid": "late-indexed",
            "title": "Late indexed cardiovascular study",
            "firstPublicationDate": "2026-08-01",
            "abstractText": "Abstract.",
        }
        merged = weekly.merge_candidate_pool([], [item], date(2026, 9, 27))
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0][weekly.DETECTED_AT], "2026-09-27")
        self.assertEqual(merged[0][weekly.LAST_SEEN_AT], "2026-09-27")

    def test_refresh_preserves_first_detection_date(self):
        previous = {
            "pmid": "same-paper",
            "title": "Original title",
            "firstPublicationDate": "2026-09-20",
            weekly.DETECTED_AT: "2026-09-21",
            weekly.LAST_SEEN_AT: "2026-09-21",
        }
        refreshed = {
            "pmid": "same-paper",
            "doi": "10.1000/newly-added-doi",
            "title": "Updated title",
            "firstPublicationDate": "2026-09-20",
        }
        merged = weekly.merge_candidate_pool([previous], [refreshed], date(2026, 9, 27))
        self.assertEqual(merged[0][weekly.DETECTED_AT], "2026-09-21")
        self.assertEqual(merged[0][weekly.LAST_SEEN_AT], "2026-09-27")
        self.assertEqual(merged[0]["title"], "Updated title")

    def test_weekly_remainder_uses_detection_cycle_and_excludes_guidelines(self):
        pool = [
            {"pmid": "1", "title": "Older paper detected now", "firstPublicationDate": "2026-08-01", weekly.DETECTED_AT: "2026-09-27"},
            {"pmid": "2", "title": "Clinical guideline", "firstPublicationDate": "2026-09-27", weekly.DETECTED_AT: "2026-09-27"},
            {"pmid": "3", "title": "Previous cycle paper", "firstPublicationDate": "2026-09-25", weekly.DETECTED_AT: "2026-09-25"},
        ]
        remainder = weekly.build_weekly_remainder(pool, date(2026, 9, 27))
        self.assertEqual([item["pmid"] for item in remainder], ["1"])
        self.assertEqual(remainder[0][weekly.DETECTED_AT], "2026-09-27")

    def test_fetch_uses_publication_and_database_creation_dates(self):
        queries = []
        original_search = weekly.epmc_search
        original_sleep = weekly.time.sleep

        def fake_search(query, page_size=40):
            queries.append((query, page_size))
            if query.startswith("CREATION_DATE:"):
                return [{"pmid": "new-index", "title": "Newly indexed paper"}]
            return []

        try:
            weekly.epmc_search = fake_search
            weekly.time.sleep = lambda _: None
            records = weekly.fetch_recent(date(2026, 9, 27))
        finally:
            weekly.epmc_search = original_search
            weekly.time.sleep = original_sleep

        self.assertEqual(len(records), 1)
        self.assertTrue(any(q.startswith("FIRST_PDATE:") for q, _ in queries))
        self.assertTrue(any(q.startswith("CREATION_DATE:") for q, _ in queries))

    def test_atherosclerosis_and_cardiomyopathy_are_cardiovascular(self):
        for disease in ("atherosclerosis", "cardiomyopathy", "dyslipidemia"):
            with self.subTest(disease=disease):
                self.assertTrue(weekly.cardiovascular_relevance({
                    "title": f"Clinical outcomes in {disease}",
                    "abstractText": f"Clinical research evaluating {disease} in patients.",
                }))

    def test_weekly_selection_accepts_late_indexed_paper_but_not_previous_issue(self):
        paper = {
            "pmid": "new-article",
            "title": "Randomized coronary trial of cardiovascular outcomes",
            "firstPublicationDate": "2026-09-20",
            weekly.DETECTED_AT: "2026-10-07",
            "abstractText": "Randomized clinical trial assessing myocardial infarction and cardiovascular mortality.",
        }
        selected = weekly.select_weekly([paper], date(2026, 10, 3), date(2026, 10, 9))
        self.assertEqual([p["pmid"] for p in selected], ["new-article"])
        repeated = weekly.select_weekly([paper], date(2026, 10, 3), date(2026, 10, 9), {"pmid:new-article"})
        self.assertEqual(repeated, [])

    def test_json_write_is_atomic_and_invalid_json_is_not_silently_emptied(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "candidates.json"
            weekly.save_json(path, [{"pmid": "1"}])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), [{"pmid": "1"}])
            self.assertFalse(path.with_name("candidates.json.tmp").exists())
            path.write_text("[", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                weekly.load_json(path, [])


if __name__ == "__main__":
    unittest.main()

