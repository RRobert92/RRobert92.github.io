#!/usr/bin/env python3
"""Refresh data/publications.json from the Semantic Scholar Graph API.

Run by .github/workflows/update-publications.yml (weekly) and manually.
The site renders the committed JSON — never the live API — so the page
always loads even when the API rate-limits (it does, aggressively, for
anonymous callers) or is down.

Papers listed in EXCLUDE_DOIS are dropped (off-topic early-career work).
"""

import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

AUTHOR_ID = "15648247"  # R. Kiewisz
API = (
    f"https://api.semanticscholar.org/graph/v1/author/{AUTHOR_ID}"
    "?fields=name,paperCount,citationCount,hIndex,"
    "papers.title,papers.year,papers.venue,papers.citationCount,"
    "papers.externalIds,papers.publicationTypes"
)

# DOIs to hide from the site (kept in the metrics, just not listed).
EXCLUDE_DOIS = set()

OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "publications.json"


def fetch(url: str, attempts: int = 5) -> dict:
    """GET with backoff — Semantic Scholar 429s anonymous callers freely."""
    for i in range(attempts):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "rrobert92.github.io publication list"}
            )
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429 or i == attempts - 1:
                raise
            wait = 10 * (i + 1)
            print(f"429 from API — retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def preferred_url(ext: dict) -> str:
    if ext.get("DOI"):
        return f"https://doi.org/{ext['DOI']}"
    if ext.get("ArXiv"):
        return f"https://arxiv.org/abs/{ext['ArXiv']}"
    if ext.get("PubMed"):
        return f"https://pubmed.ncbi.nlm.nih.gov/{ext['PubMed']}/"
    return ""


def main() -> int:
    try:
        data = fetch(API)
    except Exception as e:  # noqa: BLE001 — any failure must not clobber good data
        print(f"fetch failed ({e}); leaving existing data untouched", file=sys.stderr)
        return 0 if OUT.exists() else 1

    papers = []
    for p in data.get("papers", []):
        ext = p.get("externalIds") or {}
        doi = ext.get("DOI", "")
        if doi in EXCLUDE_DOIS:
            continue
        papers.append(
            {
                "title": p.get("title", "").strip(),
                "year": p.get("year"),
                "venue": (p.get("venue") or "").strip(),
                "citations": p.get("citationCount") or 0,
                "url": preferred_url(ext),
            }
        )

    papers.sort(key=lambda p: (-p["citations"], -(p["year"] or 0)))

    out = {
        "updated": time.strftime("%Y-%m-%d", time.gmtime()),
        "source": "Semantic Scholar",
        "profile": f"https://www.semanticscholar.org/author/{AUTHOR_ID}",
        "metrics": {
            "papers": data.get("paperCount", len(papers)),
            "citations": data.get("citationCount", 0),
            "hIndex": data.get("hIndex", 0),
        },
        "papers": papers,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {OUT} — {len(papers)} papers, {out['metrics']['citations']} citations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
