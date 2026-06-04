import json
import time
from pathlib import Path
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "papers.json"


HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; accounting-tax-tracker/0.1)"
}


def clean_html(text):
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return " ".join(soup.get_text(" ").split())


def is_good_abstract(text):
    if not text:
        return False

    text = clean_html(text)
    lower = text.lower()

    bad_markers = [
        "publication date:",
        "source:",
        "author(s):",
        "sign in",
        "subscribe",
        "purchase",
        "abstracting and indexing",
        "editorial board"
    ]

    if any(marker in lower for marker in bad_markers):
        return False

    # 摘要一般不会太短
    if len(text.split()) < 35:
        return False

    return True


def fetch_abstract_from_article_page(url):
    """
    尝试从文章详情页抓摘要。
    有些网站会 403，这是正常的。
    """
    if not url:
        return ""

    try:
        response = requests.get(url, headers=HEADERS, timeout=25)
        response.raise_for_status()
    except Exception:
        return ""

    soup = BeautifulSoup(response.text, "html.parser")

    # 1. 先找网页 meta 里的摘要
    meta_names = [
        "citation_abstract",
        "dc.Description",
        "description",
        "og:description",
        "twitter:description"
    ]

    for name in meta_names:
        tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
        if tag and tag.get("content"):
            text = clean_html(tag.get("content"))
            if is_good_abstract(text):
                return text

    # 2. 再找 class/id 里带 abstract 的区域
    candidates = soup.select(
        '[class*="abstract"], [id*="abstract"], section[aria-labelledby*="abstract"]'
    )

    for candidate in candidates:
        text = clean_html(candidate.get_text(" "))
        text = text.replace("Abstract", "").strip()

        if is_good_abstract(text):
            return text

    return ""


def fetch_abstract_from_crossref(title):
    """
    根据标题从 Crossref 补摘要。
    不是所有文章都有摘要，但成功率比直接抓网页高一些。
    """
    if not title:
        return ""

    url = "https://api.crossref.org/works"

    params = {
        "query.title": title,
        "rows": 3,
        "sort": "score",
        "order": "desc"
    }

    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=25)
        response.raise_for_status()
    except Exception:
        return ""

    items = response.json().get("message", {}).get("items", [])

    for item in items:
        abstract = item.get("abstract", "")
        abstract = clean_html(abstract)

        if is_good_abstract(abstract):
            return abstract

    return ""


def reconstruct_openalex_abstract(inverted_index):
    """
    OpenAlex 的摘要是 inverted index 格式，需要还原。
    """
    if not inverted_index:
        return ""

    positions = []

    for word, indexes in inverted_index.items():
        for index in indexes:
            positions.append((index, word))

    positions.sort(key=lambda x: x[0])
    return " ".join(word for _, word in positions)


def fetch_abstract_from_openalex(title):
    """
    根据标题从 OpenAlex 补摘要。
    OpenAlex 对程序访问更友好，常常能补到摘要。
    """
    if not title:
        return ""

    url = "https://api.openalex.org/works"
    params = {
        "search": title,
        "per-page": 3
    }

    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=25)
        response.raise_for_status()
    except Exception:
        return ""

    results = response.json().get("results", [])

    for item in results:
        inverted_index = item.get("abstract_inverted_index")
        abstract = reconstruct_openalex_abstract(inverted_index)

        if is_good_abstract(abstract):
            return abstract

    return ""


def load_papers():
    if DATA_PATH.exists():
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return []


def save_papers(papers):
    DATA_PATH.write_text(
        json.dumps(papers, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def main():
    papers = load_papers()
    updated = 0

    for i, paper in enumerate(papers, start=1):
        title = paper.get("title_en") or paper.get("title") or ""
        current_abstract = paper.get("abstract_en") or paper.get("abstract") or ""
        link = paper.get("link", "")

        if is_good_abstract(current_abstract):
            continue

        print(f"[{i}/{len(papers)}] Enriching abstract: {title[:80]}")

        abstract = ""

        # 1. 优先从文章详情页抓
        abstract = fetch_abstract_from_article_page(link)

        # 2. 如果失败，用 Crossref
        if not abstract:
            abstract = fetch_abstract_from_crossref(title)

        # 3. 如果还失败，用 OpenAlex
        if not abstract:
            abstract = fetch_abstract_from_openalex(title)

        if abstract:
            paper["abstract"] = abstract
            paper["abstract_en"] = abstract
            updated += 1
            print("  abstract found")
        else:
            paper["abstract"] = ""
            paper["abstract_en"] = ""
            print("  no abstract found")

        # 稍微停顿，避免请求太快
        time.sleep(0.5)

    save_papers(papers)
    print(f"Updated abstracts for {updated} papers.")


if __name__ == "__main__":
    main()