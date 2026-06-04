import json
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin

import requests
import yaml
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "conferences.yml"
DATA_PATH = ROOT / "data" / "conferences.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

TAX_KEYWORDS = [
    "tax", "taxation", "tax accounting", "tax avoidance",
    "tax compliance", "tax policy", "tax enforcement",
    "transfer pricing", "corporate tax", "income tax",
    "book-tax", "effective tax rate", "irs", "internal revenue service",
]

EVENT_KEYWORDS = [
    "conference", "meeting", "seminar", "workshop", "symposium",
    "call for papers", "submission", "program", "webinar",
    "lecture", "presentation", "congress", "midyear", "forum",
    "annual meeting", "research session", "deadline", "doctoral consortium",
]

BAD_LINK_WORDS = [
    "login", "log in", "sign in", "register", "membership",
    "privacy", "terms", "cookie", "contact", "about",
    "sponsor", "advertise", "exhibitor", "accessibility",
    "site map", "home", "search", "newsletter", "subscribe",
    "facebook", "twitter", "x.com", "linkedin", "youtube", "instagram",
    "cart", "profile", "account", "password", "mailto:", "javascript:",
]

# 这些来源本身就是强 tax 来源：标题不含 tax 也可以保留会议/投稿相关内容
STRONG_TAX_SOURCE_IDS = {"ATA_MIDYEAR"}

MAX_ITEMS_PER_SOURCE = 25
ARCHIVE_DAYS = 365
NEW_DAYS = 7
REQUEST_TIMEOUT = 20


def utc_now():
    return datetime.now(timezone.utc)


def clean_html(text):
    if not text:
        return ""
    soup = BeautifulSoup(str(text), "html.parser")
    return " ".join(soup.get_text(" ").split())


def contains_any(text, keywords):
    lower = (text or "").lower()
    return any(keyword.lower() in lower for keyword in keywords)


def is_bad_link(title, link):
    text = f"{title} {link}".lower()
    return any(word in text for word in BAD_LINK_WORDS)


def is_strong_tax_source(source):
    return source.get("id") in STRONG_TAX_SOURCE_IDS


def is_relevant_event(source, title, description):
    """
    会议栏目不能只看标题：
    - ATA 这类来源本身就是 tax 来源，所以只要是会议/日程/投稿相关内容就保留；
    - 其他来源必须标题或描述里出现 tax 相关词。
    """
    text = f"{title} {description}".lower()
    has_tax = contains_any(text, TAX_KEYWORDS)
    has_event = contains_any(text, EVENT_KEYWORDS)

    if is_strong_tax_source(source):
        return has_event or has_tax

    return has_tax and (has_event or len((title or "").strip()) > 8)


def relevance_score(source, title, description):
    text = f"{title} {description}".lower()
    score = 0

    for keyword in TAX_KEYWORDS:
        if keyword.lower() in text:
            score += 5

    for keyword in EVENT_KEYWORDS:
        if keyword.lower() in text:
            score += 2

    if is_strong_tax_source(source):
        score += 6

    if len((title or "").split()) >= 4:
        score += 2

    if description:
        score += 2

    return score


def normalize_link(href, base_url):
    if not href:
        return ""
    href = href.strip()
    if href.startswith("#"):
        return ""
    return urljoin(base_url, href)


def extract_possible_date(text):
    if not text:
        return ""

    patterns = [
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:[–\-]\d{1,2})?,?\s+20\d{2}",
        r"\b\d{1,2}(?:[–\-]\d{1,2})?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2}",
        r"\b20\d{2}\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(0)

    return ""


def make_event(source, title, description, link, event_date="", location="", score=0):
    title = clean_html(title)
    description = clean_html(description)

    if len(description) > 500:
        description = description[:500] + "..."

    now = utc_now().isoformat()

    return {
        "source_category": "conference",
        "source_name": source["name"],
        "source_id": source["id"],
        "source_label": source.get("source_label", "Conference / Seminar"),
        "title_en": title,
        "description_en": description,
        "event_date": event_date,
        "location": location,
        "tax_related": True,
        "link": link,
        "relevance_score": score,
        "first_seen": now,
        "last_seen": now,
        "fetched_at": now,
        "is_new": True,
    }


def fetch_source_page(source):
    events = []
    url = source["url"]

    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except Exception as e:
        print(f"  failed to fetch page: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    page_text = clean_html(soup.get_text(" "))
    page_date = extract_possible_date(page_text)
    page_title = clean_html(soup.title.get_text()) if soup.title else source["name"]

    if is_relevant_event(source, page_title, page_text):
        events.append(
            make_event(
                source=source,
                title=page_title,
                description=page_text,
                link=url,
                event_date=page_date,
                score=relevance_score(source, page_title, page_text),
            )
        )

    for a in soup.find_all("a", href=True):
        title = clean_html(a.get_text())
        link = normalize_link(a.get("href"), url)

        if not link or len(title) < 8:
            continue
        if is_bad_link(title, link):
            continue

        parent = a.find_parent()
        parent_text = clean_html(parent.get_text(" ")) if parent else ""
        description = parent_text if parent_text and parent_text != title else ""

        if not is_relevant_event(source, title, description):
            continue

        events.append(
            make_event(
                source=source,
                title=title,
                description=description,
                link=link,
                event_date=extract_possible_date(description),
                score=relevance_score(source, title, description),
            )
        )

    return events


def load_existing():
    if not DATA_PATH.exists():
        return []

    try:
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"Warning: could not read existing conference data: {e}")
        return []


def item_key(event):
    return event.get("link") or event.get("title_en") or event.get("title")


def parse_dt(value):
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def merge_with_existing(existing, new_items):
    """
    保留历史会议记录：
    - 老链接再次出现：保留 first_seen，更新 last_seen；
    - 新链接：设置 first_seen 和 last_seen；
    - 本轮没抓到但一年内出现过的旧记录继续保留，避免某个网页临时失败导致栏目清空。
    """
    now = utc_now()
    existing_map = {item_key(item): item for item in existing if item_key(item)}
    merged = {}

    for item in new_items:
        key = item_key(item)
        if not key:
            continue

        old = existing_map.get(key)
        if old:
            item["first_seen"] = old.get("first_seen") or old.get("fetched_at") or item.get("first_seen")
            item["last_seen"] = now.isoformat()
        else:
            item["first_seen"] = item.get("first_seen") or now.isoformat()
            item["last_seen"] = now.isoformat()

        first_seen_dt = parse_dt(item.get("first_seen"))
        item["is_new"] = bool(first_seen_dt and first_seen_dt >= now - timedelta(days=NEW_DAYS))
        merged[key] = item

    for key, old in existing_map.items():
        if key not in merged:
            first_seen_dt = parse_dt(old.get("first_seen") or old.get("fetched_at"))
            old["is_new"] = bool(first_seen_dt and first_seen_dt >= now - timedelta(days=NEW_DAYS))
            merged[key] = old

    cutoff = now - timedelta(days=ARCHIVE_DAYS)
    kept = []

    for item in merged.values():
        first_seen = parse_dt(item.get("first_seen") or item.get("fetched_at"))
        if first_seen is None or first_seen >= cutoff:
            kept.append(item)

    return kept


def deduplicate(events):
    unique = {}

    for event in events:
        key = item_key(event)
        if not key:
            continue

        current = unique.get(key)
        if current is None or event.get("relevance_score", 0) > current.get("relevance_score", 0):
            unique[key] = event

    return list(unique.values())


def limit_per_source(events):
    grouped = {}
    for event in events:
        grouped.setdefault(event.get("source_name", "Unknown source"), []).append(event)

    limited = []
    for _source_name, items in grouped.items():
        items = sorted(items, key=lambda x: x.get("relevance_score", 0), reverse=True)
        limited.extend(items[:MAX_ITEMS_PER_SOURCE])

    return limited


def main():
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    all_new = []

    for source in config.get("sources", []):
        print(f"Fetching conference source: {source['name']}")
        events = fetch_source_page(source)
        events = deduplicate(events)
        events = sorted(events, key=lambda x: x.get("relevance_score", 0), reverse=True)
        events = events[:MAX_ITEMS_PER_SOURCE]
        print(f"  kept {len(events)} high-relevance conference/seminar items")
        all_new.extend(events)

    new_cleaned = limit_per_source(deduplicate(all_new))
    existing = load_existing()
    merged = merge_with_existing(existing, new_cleaned)

    merged = sorted(
        merged,
        key=lambda x: (x.get("relevance_score", 0), x.get("first_seen", "")),
        reverse=True,
    )

    DATA_PATH.parent.mkdir(exist_ok=True)
    DATA_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(merged)} conference/seminar items to {DATA_PATH}")


if __name__ == "__main__":
    main()
