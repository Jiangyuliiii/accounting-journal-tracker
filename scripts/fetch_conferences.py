import json
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta

import requests
import yaml
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "conferences.yml"
DATA_PATH = ROOT / "data" / "conferences.json"


HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; accounting-tax-tracker/0.1)"
}


TAX_KEYWORDS = [
    "tax", "taxation", "tax accounting", "tax avoidance",
    "tax compliance", "tax policy", "tax enforcement",
    "transfer pricing", "corporate tax", "income tax",
    "book-tax", "effective tax rate", "irs"
]


EVENT_KEYWORDS = [
    "conference", "meeting", "seminar", "workshop", "symposium",
    "call for papers", "submission", "program", "webinar",
    "lecture", "presentation", "congress", "midyear", "forum",
    "annual meeting", "research session"
]


BAD_LINK_WORDS = [
    "login", "log in", "sign in", "register", "membership",
    "privacy", "terms", "cookie", "contact", "about",
    "sponsor", "advertise", "exhibitor", "accessibility",
    "site map", "home", "search", "newsletter", "subscribe",
    "facebook", "twitter", "linkedin", "youtube", "instagram",
    "cart", "profile", "account", "password"
]


# 这些来源本身就是强 tax 来源：标题不含 tax 也可以保留
STRONG_TAX_SOURCE_IDS = {
    "ATA_MIDYEAR"
}


MAX_ITEMS_PER_SOURCE = 25
ARCHIVE_DAYS = 365
NEW_DAYS = 7


def clean_html(text):
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return " ".join(soup.get_text(" ").split())


def contains_any(text, keywords):
    lower = text.lower()
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

    return has_tax and (has_event or len(title.strip()) > 8)


def relevance_score(source, title, description):
    """
    分数越高越优先显示。
    """
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

    # 标题越具体越好，太短的降低优先级
    if len(title.split()) >= 4:
        score += 2

    # 有描述的更好
    if description:
        score += 2

    return score


def normalize_link(href, base_url):
    if not href:
        return ""

    if href.startswith("http"):
        return href

    if href.startswith("/"):
        if "aaahq.org" in base_url:
            return "https://aaahq.org" + href
        if "eaa-online.org" in base_url:
            return "https://eaa-online.org" + href
        if "ssrn.com" in base_url:
            return "https://www.ssrn.com" + href

    return href


def extract_possible_date(text):
    if not text:
        return ""

    patterns = [
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}[–\-]?\d{0,2},?\s+20\d{2}",
        r"\b\d{1,2}[–\-]\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2}",
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

now = datetime.now(timezone.utc).isoformat()

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
    "fetched_at": now
}


def fetch_source_page(source):
    events = []

    try:
        response = requests.get(source["url"], headers=HEADERS, timeout=30)
        response.raise_for_status()
    except Exception as e:
        print(f"  failed to fetch page: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    page_text = clean_html(soup.get_text(" "))
    page_date = extract_possible_date(page_text)
    page_title = clean_html(soup.title.get_text()) if soup.title else source["name"]

    # 对 ATA 这种强 tax 来源，保留会议主页摘要
    if is_relevant_event(source, page_title, page_text):
        score = relevance_score(source, page_title, page_text)

        events.append(
            make_event(
                source=source,
                title=page_title,
                description=page_text,
                link=source["url"],
                event_date=page_date,
                location="",
                score=score
            )
        )

    # 抓取相关链接
    for a in soup.find_all("a", href=True):
        title = clean_html(a.get_text())
        href = a["href"]
        link = normalize_link(href, source["url"])

        if len(title) < 8:
            continue

        if is_bad_link(title, link):
            continue

        # 链接附近的上下文，有时比标题更有用
        parent_text = ""
        parent = a.find_parent()
        if parent:
            parent_text = clean_html(parent.get_text(" "))

        description = parent_text if parent_text and parent_text != title else ""

        if not is_relevant_event(source, title, description):
            continue

        score = relevance_score(source, title, description)

        event = make_event(
            source=source,
            title=title,
            description=description,
            link=link,
            event_date=extract_possible_date(description),
            location="",
            score=score
        )

        events.append(event)

    return events


def load_existing():
    def item_key(event):
        return event.get("link") or event.get("title_en")


def parse_dt(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def merge_with_existing(existing, new_items):
    """
    保留历史会议记录：
    - 如果是老链接再次出现，保留 first_seen，更新 last_seen；
    - 如果是新链接，设置 first_seen 和 last_seen；
    - 最后只保留 first_seen 在近一年内的记录。
    """
    now = datetime.now(timezone.utc)
    existing_map = {}

    for item in existing:
        key = item_key(item)
        if key:
            existing_map[key] = item

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

        merged[key] = item

    # 把旧数据里本周没抓到、但还在一年内的也保留
    for key, old in existing_map.items():
        if key not in merged:
            merged[key] = old

    cutoff = now - timedelta(days=ARCHIVE_DAYS)
    kept = []

    for item in merged.values():
        first_seen = parse_dt(item.get("first_seen") or item.get("fetched_at"))

        if first_seen and first_seen >= cutoff:
            kept.append(item)

    return kept

def deduplicate(events):
    unique = {}

    for event in events:
        key = event.get("link") or event.get("title_en")
        current = unique.get(key)

        if not current:
            unique[key] = event
        else:
            if event.get("relevance_score", 0) > current.get("relevance_score", 0):
                unique[key] = event

    return list(unique.values())


def limit_per_source(events):
    grouped = {}

    for event in events:
        source_name = event.get("source_name", "Unknown source")
        grouped.setdefault(source_name, []).append(event)

    limited = []

    for source_name, items in grouped.items():
        items = sorted(
            items,
            key=lambda x: x.get("relevance_score", 0),
            reverse=True
        )

        limited.extend(items[:MAX_ITEMS_PER_SOURCE])

    return limited


def main():
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    all_new = []

    for source in config["sources"]:
        print(f"Fetching conference source: {source['name']}")

        try:
            events = fetch_source_page(source)
            events = deduplicate(events)
            events = sorted(
                events,
                key=lambda x: x.get("relevance_score", 0),
                reverse=True
            )
            events = events[:MAX_ITEMS_PER_SOURCE]

            print(f"  kept {len(events)} high-relevance conference/seminar items")
            all_new.extend(events)

        except Exception as e:
            print(f"  failed: {e}")

    # 为了避免旧噪音越积越多，这里不合并旧数据，直接用本轮结果覆盖
   new_cleaned = deduplicate(all_new)
new_cleaned = limit_per_source(new_cleaned)

existing = load_existing()
merged = merge_with_existing(existing, new_cleaned)

merged = sorted(
    merged,
    key=lambda x: (
        x.get("relevance_score", 0),
        x.get("first_seen", "")
    ),
    reverse=True
)

DATA_PATH.parent.mkdir(exist_ok=True)
DATA_PATH.write_text(
    json.dumps(merged, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print(f"Saved {len(merged)} conference/seminar items to {DATA_PATH}")


if __name__ == "__main__":
    main()
