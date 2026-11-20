"""Fetch Google Scholar metrics through SerpApi and write badge JSON.

The workflow publishes results/gs_data.json and results/gs_data_shieldsio.json
to an orphan branch, so the numbers can be embedded in the README without ever
running a scraper at page render time.
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "metrics" / "config.json"
OUT_DIR = ROOT / "results"
API = "https://serpapi.com/search.json"
PROFILE = "https://scholar.google.com/citations?user={sid}"


def scholar_id() -> str:
    sid = os.environ.get("SCHOLAR_ID")
    if sid:
        return sid
    return json.loads(CONFIG.read_text(encoding="utf-8"))["scholarId"]


def fetch(author_id: str, api_key: str) -> dict:
    params = {
        "engine": "google_scholar_author",
        "author_id": author_id,
        "hl": "en",
        "api_key": api_key,
    }
    url = API + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "profile-metrics/1.0"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def metrics_from(payload: dict) -> dict:
    table = (payload.get("cited_by") or {}).get("table") or []
    merged: dict = {}
    for row in table:
        merged.update(row)
    if "citations" not in merged:
        raise ValueError("response has no cited_by table")

    def total(name: str):
        block = merged.get(name) or {}
        for key in ("all",) + tuple(k for k in block if k.startswith("since_")):
            if isinstance(block.get(key), int):
                return block[key]
        return None

    citations = total("citations")
    if not isinstance(citations, int):
        raise ValueError("citations count is not an integer")
    return {
        "citations": citations,
        "hIndex": total("h_index"),
        "i10Index": total("i10_index"),
    }


def main() -> int:
    api_key = os.environ.get("SERPAPI_KEY")
    if not api_key:
        print("::error::SERPAPI_KEY is not set")
        return 1
    sid = scholar_id()
    try:
        payload = fetch(sid, api_key)
        values = metrics_from(payload)
    except Exception as error:  # noqa: BLE001 - the workflow must fail closed
        print(f"::error::could not read Scholar metrics: {error}")
        return 1

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = PROFILE.format(sid=sid)
    data = {
        "schemaVersion": 1,
        "scholarId": sid,
        "url": url,
        **values,
        "source": "serpapi",
        "updatedAt": now,
    }
    shields = {
        "schemaVersion": 1,
        "label": "citations",
        "message": str(values["citations"]),
        "color": "blue",
        "cacheSeconds": 3600,
        "updatedAt": now,
    }

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "gs_data.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (OUT_DIR / "gs_data_shieldsio.json").write_text(
        json.dumps(shields, indent=2) + "\n", encoding="utf-8"
    )
    print(f"citations={values['citations']} h-index={values['hIndex']} i10={values['i10Index']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
