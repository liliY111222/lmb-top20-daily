#!/usr/bin/env python3
"""
Generate a local page for lithium-metal battery papers in the top 20 materials
journals from the user's reference table.

Data source: OpenAlex API. No API key is required.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOOL_DIR = ROOT / "data"
DEFAULT_OUTPUT = ROOT
OPENALEX_URL = "https://api.openalex.org/works"


SEARCH_QUERIES = [
    '"lithium metal battery"',
    '"lithium metal batteries"',
    '"lithium metal anode"',
    '"Li metal battery"',
    '"Li metal batteries"',
    '"Li metal anode"',
    '"anode-free lithium"',
    '"anode free lithium"',
    '"lithium plating"',
    '"lithium stripping"',
    '"lithium dendrite"',
    '"solid-state lithium metal battery"',
    '"solid state lithium metal battery"',
]


INCLUDE_PATTERNS = [
    r"\blithium[- ]metal batter(?:y|ies)\b",
    r"\bli[- ]metal batter(?:y|ies)\b",
    r"\blithium[- ]metal anode(?:s)?\b",
    r"\bli[- ]metal anode(?:s)?\b",
    r"\banode[- ]free lithium\b",
    r"\blithium plating\b",
    r"\blithium stripping\b",
    r"\blithium dendrite(?:s)?\b",
    r"\bdendrite[- ]free lithium\b",
    r"\blithium reversibility\b",
]


EXCLUDE_PATTERNS = [
    r"\bsodium[- ]metal\b",
    r"\bpotassium[- ]metal\b",
    r"\bzinc[- ]metal\b",
    r"\blithium[- ]ion batter(?:y|ies)\b",
    r"\bli[- ]ion batter(?:y|ies)\b",
    r"\blead[- ]acid\b",
    r"\bfuel cell\b",
    r"\bsolar cell\b",
]


JOURNAL_RANKS = {
    "nature reviews materials": 1,
    "nature energy": 2,
    "progress in materials science": 3,
    "nature materials": 4,
    "escience": 5,
    "nano micro letters": 6,
    "joule": 7,
    "nature nanotechnology": 8,
    "interdisciplinary materials": 9,
    "advanced materials": 10,
    "materials science and engineering r reports": 11,
    "advanced energy materials": 12,
    "advanced powder materials": 13,
    "carbon energy": 14,
    "energychem": 15,
    "exploration": 16,
    "infomat": 17,
    "materials today": 18,
    "advanced fiber materials": 19,
    "susmat": 20,
}


def normalize_name(value: str) -> str:
    value = value.lower()
    value = value.replace("&", "and")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def load_journals(path: Path) -> set[str]:
    journals = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            journals.add(normalize_name(line))
    return journals


def inverted_index_to_text(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        for pos in positions:
            words.append((pos, word))
    words.sort()
    return " ".join(word for _, word in words)


def fetch_openalex(query: str, from_date: str, to_date: str, per_page: int) -> list[dict[str, Any]]:
    params = {
        "search": query,
        "filter": f"from_publication_date:{from_date},to_publication_date:{to_date}",
        "per-page": str(per_page),
        "sort": "publication_date:desc",
        "mailto": "battery-daily-local@example.com",
    }
    url = OPENALEX_URL + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "lmb-top20-daily-local/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("results", [])


def source_name(work: dict[str, Any]) -> str:
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    return source.get("display_name") or ""


def source_issn(work: dict[str, Any]) -> str:
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    if source.get("issn_l"):
        return source["issn_l"]
    return ", ".join(source.get("issn") or [])


def doi_url(work: dict[str, Any]) -> str:
    return work.get("doi") or work.get("id") or ""


def authors(work: dict[str, Any], limit: int = 6) -> str:
    names = []
    for entry in work.get("authorships", []):
        name = (entry.get("author") or {}).get("display_name")
        if name:
            names.append(name)
    if len(names) > limit:
        return ", ".join(names[:limit]) + " et al."
    return ", ".join(names)


def text_for_work(work: dict[str, Any]) -> str:
    return " ".join(
        [
            work.get("title") or "",
            inverted_index_to_text(work.get("abstract_inverted_index")),
        ]
    )


def keyword_score(text: str) -> int:
    score = 0
    for pattern in INCLUDE_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            score += 3
    for pattern in EXCLUDE_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            score -= 4
    return score


def classify(text: str) -> list[str]:
    lowered = text.lower()
    buckets = [
        ("Li metal anode", ["lithium metal anode", "li metal anode", "lithium reversibility"]),
        ("Anode-free", ["anode-free", "anode free", "lithium-free anode", "li-free"]),
        ("Plating/stripping", ["lithium plating", "lithium stripping", "coulombic efficiency"]),
        ("Dendrite/interface", ["dendrite", "sei", "interphase", "interface"]),
        ("Electrolyte", ["electrolyte", "solvation", "additive", "diluent"]),
        ("Solid-state LMB", ["solid-state", "solid state", "solid electrolyte", "sulfide", "garnet"]),
        ("Safety", ["thermal runaway", "safety", "short circuit"]),
        ("Characterization/modeling", ["operando", "in situ", "simulation", "modeling", "machine learning"]),
    ]
    tags = []
    for tag, words in buckets:
        if any(word in lowered for word in words):
            tags.append(tag)
    return tags[:5]


def paper_record(work: dict[str, Any]) -> dict[str, Any]:
    source = source_name(work)
    norm_source = normalize_name(source)
    text = text_for_work(work)
    return {
        "id": work.get("id"),
        "title": work.get("title") or "(Untitled)",
        "authors": authors(work),
        "journal": source,
        "journal_rank": JOURNAL_RANKS.get(norm_source),
        "issn": source_issn(work),
        "date": work.get("publication_date") or "",
        "year": work.get("publication_year"),
        "doi_url": doi_url(work),
        "cited_by_count": work.get("cited_by_count") or 0,
        "open_access": (work.get("open_access") or {}).get("is_oa", False),
        "abstract": inverted_index_to_text(work.get("abstract_inverted_index")),
        "tags": classify(text),
        "score": keyword_score(text),
    }


def collect(days: int, max_results: int, journals: set[str], per_page: int) -> list[dict[str, Any]]:
    today = dt.date.today()
    from_date = today - dt.timedelta(days=days)
    seen: set[str] = set()
    papers: list[dict[str, Any]] = []

    for query in SEARCH_QUERIES:
        try:
            works = fetch_openalex(query, from_date.isoformat(), today.isoformat(), per_page)
        except Exception as exc:
            print(f"warning: failed query {query}: {exc}", file=sys.stderr)
            continue
        time.sleep(0.2)
        for work in works:
            key = work.get("doi") or work.get("id")
            if not key or key in seen:
                continue
            seen.add(key)
            record = paper_record(work)
            if normalize_name(record["journal"]) not in journals:
                continue
            if record["score"] <= 0:
                continue
            papers.append(record)

    papers.sort(
        key=lambda item: (
            item["date"],
            -(item["journal_rank"] or 999),
            item["score"],
            item["cited_by_count"],
        ),
        reverse=True,
    )
    return papers[:max_results]


def render_html(papers: list[dict[str, Any]], days: int, journal_file: Path) -> str:
    generated = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    cards = []
    for idx, paper in enumerate(papers, 1):
        title = html.escape(paper["title"])
        journal = html.escape(paper["journal"] or "Unknown journal")
        rank = paper["journal_rank"]
        rank_text = f"Top {rank}" if rank else "Top 20"
        date = html.escape(paper["date"])
        author_text = html.escape(paper["authors"])
        abstract_raw = paper["abstract"] or ""
        abstract = html.escape(abstract_raw[:950] + ("..." if len(abstract_raw) > 950 else ""))
        url = html.escape(paper["doi_url"])
        tags = "".join(f"<span>{html.escape(tag)}</span>" for tag in paper["tags"])
        oa = "<span>Open Access</span>" if paper["open_access"] else ""
        cards.append(
            f"""
            <article class="paper">
              <div class="meta"><strong>#{idx}</strong><span>{date}</span><span>{rank_text}</span><span>{journal}</span>{oa}</div>
              <h2><a href="{url}" target="_blank" rel="noreferrer">{title}</a></h2>
              <p class="authors">{author_text}</p>
              <div class="tags">{tags}</div>
              <p class="abstract">{abstract}</p>
            </article>
            """
        )

    empty = ""
    if not papers:
        empty = """
        <section class="empty">
          <h2>No papers found in this window</h2>
          <p>Try increasing --days. Top-20 materials journals publish lithium-metal battery papers sparsely, so a daily window can be empty.</p>
        </section>
        """

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lithium Metal Battery Papers - Materials Top 20</title>
  <style>
    :root {{
      --ink: #18212f;
      --muted: #667085;
      --line: #d8dee8;
      --soft: #f5f7fb;
      --accent: #7a2e0e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
      color: var(--ink);
      background: #fff;
      line-height: 1.58;
    }}
    header {{
      border-bottom: 1px solid var(--line);
      background: linear-gradient(180deg, #fff7ed, #ffffff);
    }}
    .wrap {{
      max-width: 1080px;
      margin: 0 auto;
      padding: 28px 22px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 29px;
      letter-spacing: 0;
    }}
    .summary {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 16px;
    }}
    .pill, .meta span, .tags span {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px 10px;
      color: var(--muted);
      background: #fff;
      font-size: 13px;
    }}
    main .wrap {{
      padding-top: 22px;
    }}
    .paper {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px 20px;
      margin-bottom: 16px;
      background: #fff;
    }}
    .paper h2 {{
      font-size: 19px;
      line-height: 1.35;
      margin: 8px 0;
    }}
    .paper a {{
      color: var(--ink);
      text-decoration: none;
    }}
    .paper a:hover {{
      color: var(--accent);
      text-decoration: underline;
    }}
    .meta, .tags {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
    }}
    .meta strong {{
      color: var(--accent);
      font-size: 13px;
    }}
    .tags span {{
      background: var(--soft);
    }}
    .authors {{
      margin: 0 0 8px;
      color: var(--muted);
      font-size: 14px;
    }}
    .abstract {{
      margin: 12px 0 0;
      color: #344054;
      font-size: 14px;
    }}
    .empty {{
      border: 1px dashed var(--line);
      border-radius: 8px;
      padding: 28px;
      background: var(--soft);
    }}
    footer {{
      color: var(--muted);
      font-size: 13px;
      border-top: 1px solid var(--line);
      margin-top: 30px;
    }}
  </style>
</head>
<body>
  <header>
    <div class="wrap">
      <h1>Lithium Metal Battery Papers - Materials Top 20</h1>
      <div>Only lithium-metal battery papers from the first 20 journals in the materials impact-factor table.</div>
      <div class="summary">
        <span class="pill">Generated: {html.escape(generated)}</span>
        <span class="pill">Window: last {days} days</span>
        <span class="pill">Papers: {len(papers)}</span>
        <span class="pill">Journal list: {html.escape(journal_file.name)}</span>
      </div>
    </div>
  </header>
  <main>
    <div class="wrap">
      {empty}
      {''.join(cards)}
    </div>
  </main>
  <footer>
    <div class="wrap">Data from OpenAlex. Journal allowlist follows the user's top-20 materials journal table.</div>
  </footer>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate lithium-metal battery papers from top-20 materials journals.")
    parser.add_argument("--days", type=int, default=90, help="lookback window in days")
    parser.add_argument("--max-results", type=int, default=120, help="maximum papers to keep")
    parser.add_argument("--per-page", type=int, default=100, help="OpenAlex results per query")
    parser.add_argument("--journals", type=Path, default=TOOL_DIR / "journals_materials_top20.txt")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    journals = load_journals(args.journals)
    papers = collect(args.days, args.max_results, journals, args.per_page)

    (args.output / "papers.json").write_text(
        json.dumps(papers, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (args.output / "index.html").write_text(
        render_html(papers, args.days, args.journals),
        encoding="utf-8",
    )

    print(f"Generated {len(papers)} lithium-metal battery papers")
    print(args.output / "index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
