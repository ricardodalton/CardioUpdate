#!/usr/bin/env python3
"""Check that today's briefing is present in both GitHub and the published site."""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = os.environ["GITHUB_REPOSITORY"]
TOKEN = os.environ["GH_TOKEN"]
TODAY = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date().isoformat()
LOCAL = Path("CardioUpdate_FINAL_AUTO/data/briefings.json")


def latest_date(payload):
    if not isinstance(payload, list):
        return ""
    return max((x.get("date", "") for x in payload if isinstance(x, dict)), default="")


def fetch_json(url, authenticated=False):
    headers = {"Accept": "application/vnd.github+json" if authenticated else "application/json",
               "User-Agent": "CardioUpdate-watchdog"}
    if authenticated:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)


def main():
    try:
        local_date = latest_date(json.loads(LOCAL.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        print(f"Local briefing unreadable: {exc}")
        local_date = ""

    try:
        pages = fetch_json(f"https://api.github.com/repos/{REPO}/pages", authenticated=True)
        site_url = pages["html_url"].rstrip("/") + "/data/briefings.json"
        published_date = latest_date(fetch_json(site_url + "?watchdog=" + TODAY))
    except (KeyError, ValueError, urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"Cannot verify published briefing: {exc}")
        published_date = ""

    stale = local_date < TODAY or published_date < TODAY
    print(f"Today (Buenos Aires): {TODAY}; main: {local_date or 'missing'}; published: {published_date or 'missing'}")
    print("Recovery required." if stale else "Briefing up to date; no recovery required.")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
        out.write(f"recover={'true' if stale else 'false'}\n")


if __name__ == "__main__":
    main()
