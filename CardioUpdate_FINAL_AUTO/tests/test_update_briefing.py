import sys
import unittest
import json
import tempfile
import types
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch


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


class ClinicalCardiologyBriefingTests(unittest.TestCase):
    def source(self, number, specialty=None, title="Heart failure cohort study", pubtypes=None):
        return {
            "pmid": str(number), "title": title,
            "abstractText": "Adults with cardiovascular disease were followed for clinical outcomes.",
            "journalTitle": "Clinical journal", "source_database": "PubMed",
            "firstPublicationDate": date.today().isoformat(),
            "pubTypeList": {"pubType": pubtypes or ["Journal Article"]},
            "search_domains": [specialty or briefing.SEARCH_DOMAINS[3][0]],
        }

    def item(self, index):
        return {"source_n": index, "title": f"Novedad {index}",
                "what_happened": "Hallazgo documentado.",
                "why_relevant": "Relevancia y limitaciones.",
                "practical_implication": "Interpretación clínica prudente."}

    def test_ten_articles_keep_editorial_order_and_verified_metadata(self):
        pool = [self.source(n) for n in range(12)]
        order = list(reversed(range(12)))
        items = briefing.parsed_ai_items({"items": [self.item(i) for i in order]}, pool)
        self.assertEqual(len(items), 10)
        self.assertEqual([x["source_title"] for x in items], [pool[i]["title"] for i in order[:10]])
        self.assertEqual([x["url"] for x in items], [briefing.url(pool[i]) for i in order[:10]])
        self.assertEqual(items[0]["specialty"], briefing.SEARCH_DOMAINS[3][0])
        self.assertEqual(items[0]["publication_date"], date.today().isoformat())

    def test_prevention_terms_and_database_do_not_override_clinical_design(self):
        prevention = self.source(1, title="LDL cholesterol apoB lipoprotein(a) carotid plaque CAC score review", pubtypes=["Review"])
        hf = self.source(2, title="Heart failure treatment: a randomized trial", pubtypes=["Randomized Controlled Trial"])
        self.assertGreater(briefing.score(hf), briefing.score(prevention))
        prevention["title"] = hf["title"]
        prevention["pubTypeList"] = hf["pubTypeList"]
        prevention["source_database"] = "Europe PMC"
        self.assertEqual(briefing.score(prevention), briefing.score(hf))

    def test_systematic_review_is_not_misclassified_as_randomized_trial(self):
        review = self.source(1, title="Heart failure: systematic review of randomized trials", pubtypes=["Meta-Analysis"])
        trial = self.source(2, title="Heart failure randomized trial", pubtypes=["Randomized Controlled Trial"])
        self.assertGreater(briefing.score(trial), briefing.score(review))

    def test_all_areas_can_reach_shortlist_despite_large_prevention_pool(self):
        prevention = briefing.SEARCH_DOMAINS[0][0]
        pool = [self.source(n, prevention, "Coronary prevention randomized trial", ["Randomized Controlled Trial"]) for n in range(100)]
        for n, (specialty, _) in enumerate(briefing.SEARCH_DOMAINS[1:], 100):
            pool.append(self.source(n, specialty))
        candidates = briefing.shortlist(pool)
        self.assertEqual(len(candidates), 60)
        represented = {s for x in candidates for s in x["search_domains"]}
        self.assertEqual(represented, briefing.SPECIALTIES)

    def test_final_edition_has_no_specialty_quota(self):
        pool = [self.source(n) for n in range(10)]
        items = briefing.parsed_ai_items({"items": [self.item(n) for n in range(10)]}, pool)
        self.assertEqual(len(items), 10)
        self.assertEqual(len({x["specialty"] for x in items}), 1)

    def test_duplicate_incomplete_and_out_of_range_references_are_rejected(self):
        pool = [self.source(n) for n in range(3)]
        invalid = [self.item(0), self.item(0), self.item(99), self.item(-1), self.item(True), self.item(1.5), {"source_n": 1}]
        self.assertEqual(len(briefing.parsed_ai_items({"items": invalid}, pool)), 1)

    def test_fallback_has_ten_unique_sources_and_no_invented_findings(self):
        pool = [self.source(n) for n in range(12)]
        items = briefing.fallback_items([pool[0]] + pool)
        self.assertEqual(len(items), 10)
        self.assertEqual(len({x["url"] for x in items}), 10)
        self.assertTrue(all("no sustituye" in x["why_relevant"] for x in items))

    def test_filter_rejects_old_noncardiac_preclinical_and_isolated_cases(self):
        self.assertTrue(briefing.eligible_source(self.source(0)))
        old = self.source(1)
        old["firstPublicationDate"] = (date.today() - timedelta(days=30)).isoformat()
        noncardiac = self.source(2, title="Dental restoration study")
        noncardiac["abstractText"] = "A comparison of dental materials."
        animal = self.source(3, title="Heart failure treatment in mice")
        case = self.source(4, pubtypes=["Case Reports"])
        for source in [old, noncardiac, animal, case]:
            with self.subTest(source=source["pmid"]):
                self.assertFalse(briefing.eligible_source(source))

    def test_ai_receives_only_bounded_multispecialty_evidence(self):
        pool = [self.source(n) for n in range(70)]
        response = types.SimpleNamespace(output_text=json.dumps({"items": [self.item(59), self.item(60)]}))
        create = unittest.mock.Mock(return_value=response)
        client = types.SimpleNamespace(responses=types.SimpleNamespace(create=create))
        module = types.SimpleNamespace(OpenAI=lambda: client)
        with patch.dict(sys.modules, {"openai": module}):
            items = briefing.ai_items(pool)
        self.assertEqual(len(items), 1)
        sent = create.call_args.kwargs["input"]
        evidence = json.loads(sent.split("\nEVIDENCIA:\n", 1)[1])
        self.assertEqual(len(evidence), 60)
        self.assertIn("Selecciona 10", sent)
        self.assertIn("mayor a menor", sent)
        self.assertIn("prevención NO debe desplazar", sent)
        self.assertIn("publication_types", evidence[0])

    def test_main_keeps_cycle_history_deduplicates_and_publishes_ten(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "briefings.json"
            today = date.today()
            saturday = today - timedelta(days=(today.weekday() - 5) % 7)
            history = []
            if today > saturday:
                history = [{"date": saturday.isoformat(), "items": [{"url": briefing.url(self.source(0))}]}]
            output.write_text(json.dumps(history), encoding="utf-8")
            sources = [self.source(n) for n in range(15)]
            def select(pool):
                self.assertEqual({s for x in pool for s in x["search_domains"]}, briefing.SPECIALTIES)
                if history:self.assertNotIn(briefing.url(sources[0]), [briefing.url(x) for x in pool])
                return briefing.parsed_ai_items({"items": [self.item(n) for n in range(10)]}, pool)
            with patch.object(briefing, "OUT", output), patch.object(briefing, "pubmed_search", return_value=sources), patch.object(briefing, "epmc_search", return_value=[]), patch.object(briefing, "ai_items", side_effect=select), patch.dict("os.environ", {"OPENAI_API_KEY": "unit-test-placeholder"}):
                briefing.main()
            editions = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(editions[0]["date"], today.isoformat())
            self.assertEqual(len(editions[0]["items"]), 10)
            self.assertEqual(editions[0]["selection_policy"], briefing.SELECTION_POLICY)
            self.assertEqual(editions[0]["selection_mode"], "ai")
            self.assertEqual(editions[1:], history)


if __name__ == "__main__":
    unittest.main()

