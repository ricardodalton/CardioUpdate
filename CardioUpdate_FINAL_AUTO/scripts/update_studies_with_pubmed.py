#!/usr/bin/env python3
"""Run the existing weekly pipeline with supplemental PubMed journal discovery.

PubMed ESearch discovers newly indexed citations in the requested journals;
Europe PMC retrieves their full bibliographic records and abstracts so the
existing eligibility, weekly publication dates, deduplication and selection
rules remain unchanged. Failure of the supplemental source does not disable
the established Europe PMC thematic search.
"""
from __future__ import annotations

import os
import time

import requests

import update_studies as weekly

PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

# Explicit titles prevent broad substring matching (e.g. Heart vs Heart Rhythm).
JOURNALS = (
    "Circulation. Heart failure",
    "Circulation. Arrhythmia and electrophysiology",
    "Circulation. Cardiovascular interventions",
    "Heart rhythm",
    "EuroIntervention",
    "Journal of the American Society of Echocardiography",
    "European heart journal. Cardiovascular Imaging",
    "American heart journal",
    "International journal of cardiology",
)

# Preserve existing priorities while explicitly recognizing the nine additions.
weekly.JOURNAL_WEIGHTS.update({
    "circulation. heart failure": 5,
    "circulation. arrhythmia and electrophysiology": 5,
    "circulation. cardiovascular interventions": 5,
    "heart rhythm": 5,
    "eurointervention": 5,
    "journal of the american society of echocardiography": 5,
    "european heart journal. cardiovascular imaging": 5,
    "american heart journal": 4,
    "international journal of cardiology": 4,
})

_original_fetch_recent = weekly.fetch_recent


def pubmed_journal_records() -> list[dict]:
    # Indexing-date overlap catches articles entered after their publication date.
    term = "(" + " OR ".join('"' + name + '"[ta]' for name in JOURNALS) + ")"
    params = {
        "db": "pubmed", "term": term, "retmode": "json", "retmax": "500",
        "sort": "pub_date", "datetype": "edat", "reldate": "14",
        "tool": "CardioUpdate", "email": os.environ.get("NCBI_EMAIL", ""),
    }
    if not params["email"]:
        del params["email"]
    if os.environ.get("NCBI_API_KEY"):
        params["api_key"] = os.environ["NCBI_API_KEY"]
    response = requests.get(PUBMED_ESEARCH, params=params, timeout=35,
                            headers={"User-Agent": "CardioUpdate/5.0 (weekly journal discovery)"})
    response.raise_for_status()
    result = response.json().get("esearchresult") or {}
    ids = list(dict.fromkeys(result.get("idlist") or []))
    if int(result.get("count") or 0) > len(ids):
        print("PubMed: result cap reached; some indexed citations may not be retrieved.")
    found: dict[str, dict] = {}
    for offset in range(0, len(ids), 20):
        batch = ids[offset:offset + 20]
        query = "(" + " OR ".join("EXT_ID:" + pmid for pmid in batch) + ")"
        for item in weekly.epmc_search(query, page_size=40):
            key = weekly.candidate_key(item)
            if key and item.get("title"):
                found[key] = item
        # Respect the NCBI/E-utilities default request-rate guidance.
        time.sleep(0.36)
    print(f"PubMed: {len(ids)} PMIDs in nine journals; {len(found)} full records retrieved via Europe PMC.")
    return list(found.values())


def fetch_recent_with_pubmed() -> list[dict]:
    thematic: list[dict] = []
    try:
        thematic = _original_fetch_recent()
    except Exception as exc:
        print(f"Europe PMC thematic search failed: {exc}")
    supplemental: list[dict] = []
    try:
        supplemental = pubmed_journal_records()
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        print(f"PubMed supplemental search unavailable: {exc}")
    merged: dict[str, dict] = {}
    # Use PMID where possible to merge PubMed and Europe PMC records with
    # differing DOI completeness; retain the original candidate key otherwise.
    for item in thematic + supplemental:
        key = ("pmid:" + str(item["pmid"]).strip()) if item.get("pmid") else weekly.candidate_key(item)
        if key:
            merged[key] = item
    if not merged:
        raise RuntimeError("Neither thematic Europe PMC nor PubMed journal discovery returned results.")
    print(f"CardioUpdate: {len(thematic)} thematic + {len(supplemental)} journal records; {len(merged)} unique candidates.")
    return list(merged.values())


weekly.fetch_recent = fetch_recent_with_pubmed

if __name__ == "__main__":
    weekly.main()
