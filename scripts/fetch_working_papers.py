import json
import re
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import quote_plus

import requests
import yaml
import feedparser
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "working_papers.yml"
DATA_PATH = ROOT / "data" / "working_papers.json"


TAX_KEYWORDS = [
    "tax", "taxation", "tax avoidance", "tax aggressiveness",
    "tax planning", "tax enforcement", "tax compliance",
    "tax policy", "tax disclosure", "tax haven", "irs",
    "book-tax", "book tax", "effective tax rate", "etr",
    "deferred tax", "tax loss", "tax losses", "nol",
    "transfer pricing", "corporate tax", "income tax",
    "book-tax differences"
]


ACCOUNTING_ECON_KEYWORDS = [
    "accounting", "financial reporting", "disclosure", "earnings",
    "firm", "firms", "corporate", "capital market", "investor",
    "economics", "finance", "compliance", "enforcement"
]


def clean_html(text):
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return " ".join(soup.get_text(" ").split())


def contains_any(text, keywords):
    text = text.lower()
    return any(keyword.lower() in text for keyword in keywords)


def is_relevant_tax_working_paper(title, abstract):
    text = f"{title} {abstract}".lower()

    tax_patterns = [
        r"\btax\b",
        r"\btaxes\b",
        r"\btaxation\b",
        r"\btaxable\b",
        r"\btaxpayer[s]?\b",
        r"\btax avoidance\b",
        r"\btax aggressiveness\b",
        r"\btax planning\b",
        r"\btax enforcement\b",
        r"\btax compliance\b",
        r"\btax policy\b",
        r"\btax disclosure\b",
        r"\btax haven[s]?\b",
        r"\bbook[- ]tax\b",
        r"\beffective tax rate[s]?\b",
        r"\bdeferred tax\b",
        r"\btax loss(?:es)?\b",
        r"\bnol[s]?\b",
        r"\btransfer pricing\b",
        r"\bcorporate tax\b",
        r"\bincome tax\b",
        r"\birs\b"
    ]

    has_tax = any(re.search(pattern, text) for pattern in tax_patterns)
    has_accounting_or_econ = contains_any(text, ACCOUNTING_ECON_KEYWORDS)

    return has_tax and has_accounting_or_econ


def get_crossref_date(item):
    date_fields = [
        "posted",
        "published-print",
        "published-online",
        "published",
        "created"
    ]

    for field in date_fields:
        date_obj = item.get(field)
        if not date_obj:
            continue

        date_parts = date_obj.get("date-parts")
        if not date_parts:
            continue

        parts = date_parts[0]
        if len(parts) >= 3:
            return f"{parts[0]}-{parts[1]:02d}-{parts[2]:02d}"
        if len(parts) == 2:
            return f"{parts[0]}-{parts[1]:02d}"
        if len(parts) == 1:
            return str(parts[0])

    return ""


def get_crossref_authors(item):
    authors = []

    for author in item.get("author", []):
        given = author.get("given", "")
        family = author.get("family", "")

        name = f"{given} {family}".strip()
        if name:
            authors.append(name)

    return authors


def make_working_paper(source_name, source_id, title, abstract, link, authors=None, posted_date="", doi=""):
    title = clean_html(title)
    abstract = clean_html(abstract)

    return {
        "source_category": "working_paper",
        "source_name": source_name,
        "source_id": source_id,
        "title_en": title,
        "title_zh": "",
        "abstract_en": abstract,
        "abstract_zh": "",
        "authors": authors or [],
        "posted_date": posted_date,
        "tax_related": True,
        "link": link,
        "doi": doi,
        "fetched_at": datetime.now(timezone.utc).isoformat()
    }


def fetch_crossref(source):
    papers = []
    headers = {
        "User-Agent": "accounting-tax-tracker/0.1 (mailto:example@example.com)"
    }

    for query in source.get("queries", []):
        print(f"    Crossref query: {query}")

        params = {
            "query.bibliographic": query,
            "rows": 20,
            "sort": "published",
            "order": "desc"
        }

        try:
            response = requests.get(
                source["url"],
                params=params,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
        except Exception as e:
            print(f"      failed: {e}")
            continue

        data = response.json()
        items = data.get("message", {}).get("items", [])

        for item in items:
            titles = item.get("title", [])
            title = titles[0] if titles else ""

            abstract = item.get("abstract", "")
            link = item.get("URL", "")
            doi = item.get("DOI", "")

            if not title:
                continue

            if not is_relevant_tax_working_paper(title, abstract):
                continue

            source_type = item.get("type", "")

            # 优先保留 posted-content / report / working paper 相关内容；
            # 如果 type 不是这些，但标题摘要高度相关，也先保留。
            source_label = source["name"]
            if source_type:
                source_label = f"{source['name']} · {source_type}"

            paper = make_working_paper(
                source_name=source_label,
                source_id=source["id"],
                title=title,
                abstract=abstract,
                link=link,
                authors=get_crossref_authors(item),
                posted_date=get_crossref_date(item),
                doi=doi
            )

            papers.append(paper)

    return papers


def fetch_arxiv(source):
    papers = []

    for query in source.get("queries", []):
        print(f"    arXiv query: {query}")

        search_query = f'all:"{query}"'

        url = (
            source["url"]
            + "?search_query="
            + quote_plus(search_query)
            + "&start=0&max_results=20&sortBy=submittedDate&sortOrder=descending"
        )

        feed = feedparser.parse(url)

        for entry in feed.entries:
            title = entry.get("title", "")
            abstract = entry.get("summary", "")
            link = entry.get("link", "")

            if not is_relevant_tax_working_paper(title, abstract):
                continue

            authors = []
            if "authors" in entry:
                authors = [
                    a.get("name", "")
                    for a in entry.authors
                    if a.get("name")
                ]

            posted_date = entry.get("published", "") or entry.get("updated", "")

            paper = make_working_paper(
                source_name=source["name"],
                source_id=source["id"],
                title=title,
                abstract=abstract,
                link=link,
                authors=authors,
                posted_date=posted_date,
                doi=""
            )

            papers.append(paper)

    return papers


def load_existing():
    if DATA_PATH.exists():
        try:
            return json.loads(DATA_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


def deduplicate(papers):
    unique = {}

    for paper in papers:
        key = paper.get("doi") or paper.get("link") or paper.get("title_en")
        unique[key] = paper

    return list(unique.values())


def main():
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    all_new = []

    for source in config["sources"]:
        print(f"Fetching working papers from {source['name']}...")

        try:
            if source["id"] == "CROSSREF":
                papers = fetch_crossref(source)
            elif source["id"] == "ARXIV":
                papers = fetch_arxiv(source)
            else:
                papers = []

            print(f"  found {len(papers)} tax-related working papers")
            all_new.extend(papers)

        except Exception as e:
            print(f"  failed: {e}")

    existing = load_existing()
    merged = deduplicate(existing + all_new)

    DATA_PATH.parent.mkdir(exist_ok=True)
    DATA_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"Saved {len(merged)} working papers to {DATA_PATH}")


if __name__ == "__main__":
    main()