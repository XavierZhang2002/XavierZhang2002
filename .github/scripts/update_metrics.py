"""Refresh the profile metric badges.

Collects Google Scholar citations (SerpApi) and the star total of the listed
repositories, then renders small light/dark SVG badges referenced from the
profile README. Missing or invalid data keeps the previous snapshot, so a
badge never silently drops to zero.
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "metrics" / "config.json"
STATS = ROOT / "metrics" / "stats.json"
OUT_DIR = ROOT / "metrics"

SERPAPI = "https://serpapi.com/search.json"
GITHUB_REPO_API = "https://api.github.com/repos/{repo}"
SCHOLAR_PROFILE = "https://scholar.google.com/citations?user={sid}"

LIGHT = dict(bg="#ffffff", border="#d1d9e0", label="#59636e", value="#1f2328")
DARK = dict(bg="#151b23", border="#3d444d", label="#9198a1", value="#f0f6fc")


def fetch_json(url, headers=None, timeout=45):
    request = urllib.request.Request(
        url,
        headers=headers or {"Accept": "application/json", "User-Agent": "profile-metrics/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def scholar_citations(scholar_id, api_key):
    params = {
        "engine": "google_scholar_author",
        "author_id": scholar_id,
        "hl": "en",
        "api_key": api_key,
    }
    payload = fetch_json(SERPAPI + "?" + urllib.parse.urlencode(params))
    table = (payload.get("cited_by") or {}).get("table") or []
    merged = {}
    for row in table:
        merged.update(row)

    def total(name):
        block = merged.get(name) or {}
        for key in ("all",) + tuple(k for k in block if k.startswith("since_")):
            if isinstance(block.get(key), int):
                return block[key]
        return None

    citations = total("citations")
    if not isinstance(citations, int):
        raise ValueError("no citation count in the SerpApi response")
    return {"citations": citations, "hIndex": total("h_index"), "i10Index": total("i10_index")}


S2_API = (
    "https://api.semanticscholar.org/graph/v1/author/{aid}"
    "?fields=name,citationCount,hIndex,paperCount"
)


def semantic_scholar(author_id):
    data = fetch_json(S2_API.format(aid=author_id))
    citations = data.get("citationCount")
    if not isinstance(citations, int):
        raise ValueError("no citationCount in the Semantic Scholar response")
    return {
        "citations": citations,
        "hIndex": data.get("hIndex"),
        "paperCount": data.get("paperCount"),
        "source": "semantic-scholar",
    }


def repo_stars(repo, token):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-metrics/1.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = fetch_json(GITHUB_REPO_API.format(repo=repo), headers)
    stars = data.get("stargazers_count")
    if not isinstance(stars, int):
        raise ValueError("no stargazers_count for " + repo)
    return {"repo": data["full_name"], "url": data["html_url"], "stars": stars}


def badge(label, value, palette, height=26, font_size=12):
    label_w = int(len(label) * 6.55) + 20
    value_w = int(len(str(value)) * 7.1) + 20
    width = label_w + value_w
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" role="img" '
        'aria-label="{aria}">'
        "<title>{aria}</title>"
        '<rect x=".5" y=".5" width="{rw}" height="{rh}" rx="6" fill="{bg}" stroke="{border}"/>'
        '<text x="{lx}" y="17" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif" '
        'font-size="{fs}" fill="{lc}">{label}</text>'
        '<text x="{vx}" y="17" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif" '
        'font-size="{fs}" font-weight="700" fill="{vc}">{value}</text>'
        "</svg>\n"
    ).format(
        w=width, h=height, rw=width - 1, rh=height - 1, fs=font_size,
        aria=escape("%s: %s" % (label, value)),
        bg=palette["bg"], border=palette["border"], lc=palette["label"], vc=palette["value"],
        lx=10, vx=label_w + 10, label=escape(label), value=escape(str(value)),
    )


def write_badge(name, label, value):
    for suffix, palette in (("", LIGHT), ("-dark", DARK)):
        (OUT_DIR / f"{name}{suffix}.svg").write_text(
            badge(label, value, palette), encoding="utf-8"
        )


def main():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    previous = json.loads(STATS.read_text(encoding="utf-8")) if STATS.exists() else {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stats = {"schemaVersion": 1, "updatedAt": now, "sources": {}}

    scholar_id = os.environ.get("SCHOLAR_ID") or config["scholarId"]
    api_key = os.environ.get("SERPAPI_KEY")
    scholar = None

    if api_key:
        try:
            scholar = scholar_citations(scholar_id, api_key)
            scholar["source"] = "serpapi"
            scholar["url"] = SCHOLAR_PROFILE.format(sid=scholar_id)
        except Exception as error:  # noqa: BLE001
            print("::warning::SerpApi fetch failed: %s" % error)
    else:
        print("::notice::SERPAPI_KEY is not set, falling back to Semantic Scholar")

    if scholar is None:
        s2_id = config.get("semanticScholarId")
        if s2_id:
            try:
                scholar = semantic_scholar(s2_id)
                scholar["url"] = config.get("semanticScholarUrl", "https://www.semanticscholar.org/author/" + s2_id)
            except Exception as error:  # noqa: BLE001
                print("::warning::Semantic Scholar fetch failed: %s" % error)

    if scholar is None:
        scholar = previous.get("citations") or {}
    if not isinstance(scholar.get("citations"), int):
        print("::error::no citation snapshot available")
        return 1
    stats["citations"] = scholar

    token = os.environ.get("GITHUB_TOKEN", "")
    repos, stars = [], 0
    for repo in config["repositories"]:
        try:
            entry = repo_stars(repo, token)
        except Exception as error:  # noqa: BLE001
            print("::warning::stars fetch failed for %s: %s" % (repo, error))
            continue
        repos.append(entry)
        stars += entry["stars"]
    if not repos:
        repos = previous.get("repositories") or []
        stars = sum(r["stars"] for r in repos)
    if not repos:
        print("::error::no star snapshot available")
        return 1
    stats["repositories"] = repos
    stats["stars"] = stars

    STATS.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_badge("citations", "Scholar citations", stats["citations"]["citations"])
    write_badge("project-stars", "Project stars", stars)
    print("citations=%s stars=%s" % (stats["citations"]["citations"], stars))
    return 0


if __name__ == "__main__":
    sys.exit(main())
