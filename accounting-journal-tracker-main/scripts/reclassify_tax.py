import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAPERS_PATH = ROOT / "data" / "papers.json"
WORKING_PAPERS_PATH = ROOT / "data" / "working_papers.json"


TITLE_TAX_PATTERNS = [
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
    r"\btax loss carryforward[s]?\b",
    r"\btransfer pricing\b",
    r"\bcorporate tax\b",
    r"\bincome tax\b",
    r"\btaxable income\b",
    r"\btax shelter[s]?\b",
    r"\btax audit[s]?\b",
    r"\btax authority\b",
    r"\btax authorities\b",
    r"\btax reform\b",
    r"\btax regulation[s]?\b",
    r"\btax expense\b",
    r"\btax rate[s]?\b",
    r"\bIRS\b",
]

ABSTRACT_STRONG_TAX_PATTERNS = [
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
    r"\btax loss carryforward[s]?\b",
    r"\btransfer pricing\b",
    r"\bcorporate tax\b",
    r"\bincome tax\b",
    r"\btaxable income\b",
    r"\btax shelter[s]?\b",
    r"\btax audit[s]?\b",
    r"\btax authority\b",
    r"\btax authorities\b",
    r"\btax reform\b",
    r"\btax regulation[s]?\b",
    r"\btax expense\b",
    r"\btax rate[s]?\b",
    r"\bIRS\b",
]

ABSTRACT_BASIC_TAX_PATTERNS = [
    r"\btax\b",
    r"\btaxes\b",
    r"\btaxation\b",
    r"\btaxable\b",
    r"\btaxpayer[s]?\b",
]


def load_json(path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


def save_json(path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def matched_patterns(patterns, text, ignore_case=True):
    flags = re.IGNORECASE if ignore_case else 0
    matched = []

    for pattern in patterns:
        if re.search(pattern, text or "", flags=flags):
            matched.append(pattern)

    return matched


def count_pattern_matches(patterns, text):
    count = 0

    for pattern in patterns:
        count += len(re.findall(pattern, text or "", flags=re.IGNORECASE))

    return count


def is_tax_related(title, abstract):
    title = title or ""
    abstract = abstract or ""

    matched = []

    # 1. 标题出现 tax 相关词，直接判定为 Tax
    title_matches = matched_patterns(TITLE_TAX_PATTERNS, title)
    matched.extend([f"title:{m}" for m in title_matches])

    if title_matches:
        return True, matched

    # 2. 摘要出现强 tax 词，判定为 Tax
    strong_abstract_matches = matched_patterns(ABSTRACT_STRONG_TAX_PATTERNS, abstract)
    matched.extend([f"abstract:{m}" for m in strong_abstract_matches])

    if strong_abstract_matches:
        return True, matched

    # 3. 摘要里只有普通 tax / taxes / taxation，至少出现 2 次才判定为 Tax
    basic_count = count_pattern_matches(ABSTRACT_BASIC_TAX_PATTERNS, abstract)
    if basic_count >= 2:
        matched.append(f"abstract:basic_tax_count={basic_count}")
        return True, matched

    return False, matched


def reclassify_file(path, title_key="title_en", abstract_key="abstract_en"):
    items = load_json(path)

    changed = 0
    tax_count = 0

    for item in items:
        title = item.get(title_key) or item.get("title") or ""
        abstract = item.get(abstract_key) or item.get("abstract") or ""

        old_value = item.get("tax_related", False)
        new_value, matched = is_tax_related(title, abstract)

        item["tax_related"] = new_value
        item["tax_match_reason"] = matched

        if old_value != new_value:
            changed += 1

        if new_value:
            tax_count += 1

    save_json(path, items)

    print(f"{path.name}: {len(items)} items, {tax_count} tax-related, {changed} changed.")


def main():
    reclassify_file(PAPERS_PATH)
    reclassify_file(WORKING_PAPERS_PATH)


if __name__ == "__main__":
    main()