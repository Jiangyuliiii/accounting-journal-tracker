import json
import re
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import quote_plus

import feedparser
import yaml
import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "journals.yml"
DATA_PATH = ROOT / "data" / "papers.json"


TAX_KEYWORDS = [
    "tax", "taxation", "tax avoidance", "tax aggressiveness",
    "tax planning", "tax enforcement", "tax compliance",
    "tax policy", "tax disclosure", "tax haven", "irs",
    "book-tax", "book tax", "effective tax rate", "etr",
    "deferred tax", "tax loss", "tax losses", "nol",
    "transfer pricing", "corporate tax", "income tax"
]


METHOD_RULES = {
    "Archival empirical": [
        "regression", "sample", "firm-year", "compustat", "crsp",
        "difference-in-differences", "did", "event study",
        "instrumental variable", "panel data", "empirical analysis"
    ],
    "Experiment": [
        "experiment", "participants", "random assignment",
        "treatment condition", "laboratory"
    ],
    "Analytical / Theory": [
        "model", "equilibrium", "theoretical", "analytical model"
    ],
    "Survey / Interview": [
        "survey", "interview", "questionnaire"
    ],
    "Field study": [
        "field experiment", "field data", "site visit"
    ]
}


ARTICLE_KEYWORDS = [
    "accounting", "tax", "audit", "earnings", "disclosure",
    "financial", "firm", "investor", "analyst", "manager",
    "reporting", "governance", "information", "capital market",
    "restatement", "misstatement", "earnings management",
    "tax avoidance", "taxation", "carbon", "mandatory"
]


HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; accounting-tax-tracker/0.1)"
}


def clean_html(text):
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return " ".join(soup.get_text(" ").split())


def looks_like_metadata(text):
    if not text:
        return False

    lower = text.lower()

    metadata_markers = [
        "publication date:",
        "source:",
        "author(s):",
        "volume",
        "issue",
        "available online"
    ]

    return any(marker in lower for marker in metadata_markers)


def extract_authors_from_metadata(text):
    if not text:
        return []

    match = re.search(r"Author\(s\):\s*(.*)", text)
    if not match:
        return []

    authors_text = match.group(1).strip()
    authors_text = re.sub(r"\s+", " ", authors_text)

    if not authors_text:
        return []

    return [a.strip() for a in authors_text.split(",") if a.strip()]


def extract_date_from_metadata(text):
    if not text:
        return ""

    match = re.search(r"Publication date:\s*(.*?)(Source:|Author\(s\):|$)", text)
    if not match:
        return ""

    return match.group(1).strip()


def is_tax_related(title, abstract):
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

    return any(re.search(pattern, text) for pattern in tax_patterns)


def infer_method(title, abstract):
    text = f"{title} {abstract}".lower()
    for method, keywords in METHOD_RULES.items():
        if any(keyword in text for keyword in keywords):
            return method
    return "Unclassified"


def normalize_link(href, base_url):
    if not href:
        return ""

    if href.startswith("http"):
        return href

    if href.startswith("/"):
        if "springer.com" in base_url:
            return "https://link.springer.com" + href
        if "wiley.com" in base_url:
            return "https://onlinelibrary.wiley.com" + href
        if "aaahq.org" in base_url:
            return "https://publications.aaahq.org" + href
        if "sciencedirect.com" in base_url:
            return "https://www.sciencedirect.com" + href

    return href


def get_crossref_date(item):
    date_fields = [
        "published-online",
        "published-print",
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


def make_paper(journal, section, title, abstract, link, authors=None, published="", source_info="", doi=""):
    title = clean_html(title)
    abstract = clean_html(abstract)
    source_info = clean_html(source_info)

    return {
        "source_category": "journal_article",
        "journal_id": journal["id"],
        "journal": journal["name"],
        "section": section["label"],
        "title": title,
        "title_en": title,
        "title_zh": "",
        "authors": authors or [],
        "published": published,
        "abstract": abstract,
        "abstract_en": abstract,
        "abstract_zh": "",
        "source_info": source_info,
        "method": infer_method(title, abstract),
        "tax_related": is_tax_related(title, abstract),
        "link": link,
        "doi": doi,
        "fetched_at": datetime.now(timezone.utc).isoformat()
    }


def fetch_rss(journal, section):
    feed = feedparser.parse(section["url"])
    papers = []

    for entry in feed.entries:
        title = entry.get("title", "")
        raw_summary = clean_html(entry.get("summary", ""))
        link = entry.get("link", "")

        authors = []
        if "authors" in entry:
            authors = [
                a.get("name", "")
                for a in entry.authors
                if a.get("name")
            ]

        published = entry.get("published", "") or entry.get("updated", "")
        abstract = ""
        source_info = ""

        if looks_like_metadata(raw_summary):
            source_info = raw_summary

            extracted_authors = extract_authors_from_metadata(raw_summary)
            if extracted_authors and not authors:
                authors = extracted_authors

            extracted_date = extract_date_from_metadata(raw_summary)
            if extracted_date and not published:
                published = extracted_date
        else:
            abstract = raw_summary

        paper = make_paper(
            journal=journal,
            section=section,
            title=title,
            abstract=abstract,
            link=link,
            authors=authors,
            published=published,
            source_info=source_info
        )

        papers.append(paper)

    return papers


def fetch_webpage_basic(journal, section):
    response = requests.get(section["url"], headers=HEADERS, timeout=25)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    papers = []

    for a in soup.find_all("a", href=True):
        title = clean_html(a.get_text())
        href = a["href"]
        link = normalize_link(href, section["url"])

        if len(title) < 18:
            continue

        lower_title = title.lower()

        bad_words = [
            "submit", "subscribe", "sign in", "log in", "register",
            "alerts", "permissions", "about", "editorial board",
            "author guidelines", "view all", "current issue",
            "browse", "search", "recommend", "american taxation association"
        ]

        if any(bad in lower_title for bad in bad_words):
            continue

        if not any(keyword in lower_title for keyword in ARTICLE_KEYWORDS):
            continue

        paper = make_paper(
            journal=journal,
            section=section,
            title=title,
            abstract="",
            link=link,
            authors=[],
            published="",
            source_info=""
        )

        papers.append(paper)

    unique = {}
    for paper in papers:
        key = paper.get("link") or paper.get("title")
        unique[key] = paper

    return list(unique.values())[:30]


def fetch_tar_crossref_fallback(journal):
    """
    TAR 官网容易 403。
    这里用 Crossref 作为备用来源，保证 The Accounting Review 不会从网页里消失。
    """
    print("  TAR fallback: Crossref")

    section = {
        "label": "Crossref Fallback / Recent Articles"
    }

    url = "https://api.crossref.org/works"

    params = {
        "query.container-title": "The Accounting Review",
        "filter": "issn:1558-7967,type:journal-article",
        "rows": 30,
        "sort": "published",
        "order": "desc"
    }

    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except Exception as e:
        print(f"    TAR Crossref fallback failed: {e}")
        return []

    items = response.json().get("message", {}).get("items", [])
    papers = []

    for item in items:
        title_list = item.get("title", [])
        title = title_list[0] if title_list else ""

        if not title:
            continue

        abstract = clean_html(item.get("abstract", ""))
        link = item.get("URL", "")
        doi = item.get("DOI", "")
        published = get_crossref_date(item)
        authors = get_crossref_authors(item)

        paper = make_paper(
            journal=journal,
            section=section,
            title=title,
            abstract=abstract,
            link=link,
            authors=authors,
            published=published,
            source_info="Source: Crossref fallback because publisher page blocked script access.",
            doi=doi
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
        key = paper.get("doi") or paper.get("link") or paper.get("title")
        unique[key] = paper

    return list(unique.values())


def main():
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    all_new = []

    for journal in config["journals"]:
        print(f"Fetching {journal['id']}...")

        journal_new = []

        for section in journal.get("sections", []):
            print(f"  Section: {section['label']}")

            try:
                if section["source_type"] == "rss":
                    papers = fetch_rss(journal, section)
                else:
                    papers = fetch_webpage_basic(journal, section)

                print(f"    found {len(papers)} papers")
                journal_new.extend(papers)

            except Exception as e:
                print(f"    failed: {e}")

        # TAR 如果官网抓不到，用 Crossref 兜底
        if journal["id"] == "TAR" and len(journal_new) == 0:
            fallback_papers = fetch_tar_crossref_fallback(journal)
            print(f"    fallback found {len(fallback_papers)} papers")
            journal_new.extend(fallback_papers)

        all_new.extend(journal_new)

    existing = load_existing()
    merged = deduplicate(existing + all_new)

    DATA_PATH.parent.mkdir(exist_ok=True)
    DATA_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"Saved {len(merged)} papers to {DATA_PATH}")


if __name__ == "__main__":
    main()