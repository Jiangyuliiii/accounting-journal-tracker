import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from jinja2 import Template


ROOT = Path(__file__).resolve().parents[1]
JOURNAL_DATA_PATH = ROOT / "data" / "papers.json"
WORKING_PAPER_DATA_PATH = ROOT / "data" / "working_papers.json"
CONFERENCE_DATA_PATH = ROOT / "data" / "conferences.json"
SITE_DIR = ROOT / "docs"
INDEX_PATH = SITE_DIR / "index.html"

JOURNAL_ORDER = ["TAR", "JAE", "JAR", "CAR", "RAST"]
NEW_DAYS = 7


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>Accounting & Tax Research Weekly Tracker</title>
  <link rel="stylesheet" href="style.css">
</head>

<body>
  <header>
    <h1>Accounting & Tax Research Weekly Tracker</h1>
    <p>这是江小毛建立的学术研究辅助网站，用于自己的会计学与税收方向论文写作。</p>
    <p>网站主要进行一键式会计学五大期刊最新文献追踪，方便快速浏览前沿动态。</p>
    <p>优先追踪 Early Access / Articles in Press / Online First / Most Recent，并单独整理 Tax working papers 与 Tax conferences/seminars。</p>
    <p class="updated">Last updated: {{ updated_at }}</p>
  </header>

  <main>
    <section class="summary">
      <div>
        <strong>{{ total }}</strong>
        <span>期刊文献</span>
      </div>
      <div>
        <strong>{{ tax_total }}</strong>
        <span>Tax 期刊文献</span>
      </div>
      <div>
        <strong>{{ working_total }}</strong>
        <span>Tax Working Papers</span>
      </div>
      <div>
        <strong>{{ conference_total }}</strong>
        <span>Tax Conferences / Seminars</span>
      </div>
    </section>

    <nav class="top-tabs">
      <a href="#tax-section">Tax 期刊文献</a>
      <a href="#non-tax-section">非 Tax 期刊文献</a>
      <a href="#working-paper-section">Tax Working Papers</a>
      <a href="#conference-section">Tax Conferences / Seminars</a>
    </nav>

    <section id="tax-section" class="major-section tax-section">
      <h2>Tax 期刊文献</h2>
      <p class="section-note">
        识别依据：标题或摘要中包含 tax、taxation、tax avoidance、ETR、book-tax、tax loss、transfer pricing 等关键词。已使用更严格规则减少误判。
      </p>

      {% if tax_grouped %}
        {% for journal_id in journal_order %}
          {% if tax_grouped.get(journal_id) %}
            <details class="journal-block">
              <summary>
                <span>{{ journal_id }}</span>
                <span>{{ journal_counts_tax[journal_id] }} 篇</span>
              </summary>

              {% for section_name, papers in tax_grouped[journal_id].items() %}
                <div class="section-subgroup">
                  <div class="section-subtitle">
                    <span>{{ section_name }}</span>
                    <span>{{ papers | length }} 篇</span>
                  </div>

                  {% for paper in papers %}
                    <article class="card tax-card">
                      <div class="meta">
                        {{ paper.journal }} · {{ paper.section or "Unknown section" }} · {{ paper.published or "No date" }}
                      </div>

                      {% if paper.is_new %}
                        <span class="new-badge">本周新增</span>
                      {% endif %}

                      <h3>
                        <a href="{{ paper.link }}" target="_blank">
                          {{ paper.title_en or paper.title }}
                        </a>
                      </h3>

                      <div class="abstract-block">
                        <h4>Abstract</h4>
                        <p>{{ paper.abstract_en or paper.abstract or "No abstract available." }}</p>
                      </div>

                      {% if paper.source_info %}
                        <div class="source-info">
                          <h4>Source Info</h4>
                          <p>{{ paper.source_info }}</p>
                        </div>
                      {% endif %}

                      <p class="authors">
                        {% if paper.authors %}
                          Authors: {{ paper.authors | join(", ") }}
                        {% else %}
                          Authors: No author information available.
                        {% endif %}
                      </p>

                      <p>
                        <span class="tag">Method: {{ paper.method }}</span>
                        <span class="tag tax-tag">Tax</span>
                      </p>
                    </article>
                  {% endfor %}
                </div>
              {% endfor %}
            </details>
          {% endif %}
        {% endfor %}
      {% else %}
        <p class="empty">目前没有识别到 Tax 相关期刊文献。</p>
      {% endif %}
    </section>

    <section id="non-tax-section" class="major-section non-tax-section">
      <h2>非 Tax 期刊文献</h2>
      <p class="section-note">
        未被识别为 Tax 主题的期刊文献会归入此处。
      </p>

      {% if non_tax_grouped %}
        {% for journal_id in journal_order %}
          {% if non_tax_grouped.get(journal_id) %}
            <details class="journal-block">
              <summary>
                <span>{{ journal_id }}</span>
                <span>{{ journal_counts_non_tax[journal_id] }} 篇</span>
              </summary>

              {% for section_name, papers in non_tax_grouped[journal_id].items() %}
                <div class="section-subgroup">
                  <div class="section-subtitle">
                    <span>{{ section_name }}</span>
                    <span>{{ papers | length }} 篇</span>
                  </div>

                  {% for paper in papers %}
                    <article class="card">
                      <div class="meta">
                        {{ paper.journal }} · {{ paper.section or "Unknown section" }} · {{ paper.published or "No date" }}
                      </div>

                      {% if paper.is_new %}
                        <span class="new-badge">本周新增</span>
                      {% endif %}

                      <h3>
                        <a href="{{ paper.link }}" target="_blank">
                          {{ paper.title_en or paper.title }}
                        </a>
                      </h3>

                      <div class="abstract-block">
                        <h4>Abstract</h4>
                        <p>{{ paper.abstract_en or paper.abstract or "No abstract available." }}</p>
                      </div>

                      {% if paper.source_info %}
                        <div class="source-info">
                          <h4>Source Info</h4>
                          <p>{{ paper.source_info }}</p>
                        </div>
                      {% endif %}

                      <p class="authors">
                        {% if paper.authors %}
                          Authors: {{ paper.authors | join(", ") }}
                        {% else %}
                          Authors: No author information available.
                        {% endif %}
                      </p>

                      <p>
                        <span class="tag">Method: {{ paper.method }}</span>
                      </p>
                    </article>
                  {% endfor %}
                </div>
              {% endfor %}
            </details>
          {% endif %}
        {% endfor %}
      {% else %}
        <p class="empty">目前没有非 Tax 期刊文献。</p>
      {% endif %}
    </section>

    <section id="working-paper-section" class="major-section working-section">
      <h2>Tax Working Papers</h2>
      <p class="section-note">
        来源包括 Crossref、arXiv 等。后续还可以继续加入 SSRN、IDEAS/RePEc 等来源。
      </p>

      {% if working_grouped %}
        {% for source_name, papers in working_grouped.items() %}
          <details class="journal-block">
            <summary>
              <span>{{ source_name }}</span>
              <span>{{ papers | length }} 篇</span>
            </summary>

            {% for paper in papers %}
              <article class="card working-card">
                <div class="meta">
                  {{ paper.source_name }} · {{ paper.posted_date or "No date" }}
                </div>

                {% if paper.is_new %}
                  <span class="new-badge">本周新增</span>
                {% endif %}

                <h3>
                  <a href="{{ paper.link }}" target="_blank">
                    {{ paper.title_en }}
                  </a>
                </h3>

                <div class="abstract-block">
                  <h4>Abstract</h4>
                  <p>{{ paper.abstract_en or "No abstract available." }}</p>
                </div>

                <p class="authors">
                  {% if paper.authors %}
                    Authors: {{ paper.authors | join(", ") }}
                  {% else %}
                    Authors: No author information available.
                  {% endif %}
                </p>

                <p>
                  <span class="tag tax-tag">Tax Working Paper</span>
                </p>
              </article>
            {% endfor %}
          </details>
        {% endfor %}
      {% else %}
        <p class="empty">当前暂无 Tax Working Paper 数据。</p>
      {% endif %}
    </section>

    <section id="conference-section" class="major-section conference-section">
      <h2>Tax Conferences / Seminars</h2>
      <p class="section-note">
        自动检索税收、税收会计、会计会议、研讨会、征稿信息和 seminar 信息。会议栏目按来源分组，每个来源下再区分最近 {{ new_days }} 天新增条目与近一年归档条目。
      </p>

      {% if conference_by_source %}
        {% for source_name, groups in conference_by_source.items() %}
          <details class="journal-block">
            <summary>
              <span>{{ source_name }}</span>
              <span>{{ groups.total }} 条</span>
            </summary>

            <div class="conference-split">
              <h3>This Week’s New Items</h3>
              <p class="mini-note">最近 {{ new_days }} 天首次抓取到的会议、讲座、征稿或相关链接。</p>

              {% if groups.new %}
                {% for event in groups.new %}
                  <article class="card conference-card">
                    <div class="meta">
                      {{ event.source_label or "Conference / Seminar" }} · {{ event.event_date or "No date" }}
                    </div>

                    {% if event.is_new %}
                      <span class="new-badge">本周新增</span>
                    {% endif %}

                    <h3>
                      <a href="{{ event.link }}" target="_blank">
                        {{ event.title_en }}
                      </a>
                    </h3>

                    <div class="abstract-block">
                      <h4>Details</h4>
                      <p>{{ event.description_en or "No detailed description available. Only title/link was detected." }}</p>
                    </div>

                    <p class="authors">
                      First seen: {{ event.first_seen_display or "Unknown" }}
                      {% if event.last_seen_display %}
                        · Last seen: {{ event.last_seen_display }}
                      {% endif %}
                    </p>

                    <p>
                      <span class="tag conference-tag">{{ event.source_label or "Conference / Seminar" }}</span>
                      <span class="tag">New</span>
                      <span class="tag">Score: {{ event.relevance_score or 0 }}</span>
                    </p>
                  </article>
                {% endfor %}
              {% else %}
                <p class="empty">最近 {{ new_days }} 天暂无新增条目。</p>
              {% endif %}
            </div>

            <div class="conference-split archive-split">
              <h3>Past-Year Archive</h3>
              <p class="mini-note">过去一年内已检索到、但不属于最近 {{ new_days }} 天新增的会议、讲座、征稿或相关链接。</p>

              {% if groups.archive %}
                {% for event in groups.archive %}
                  <article class="card conference-card">
                    <div class="meta">
                      {{ event.source_label or "Conference / Seminar" }} · {{ event.event_date or "No date" }}
                    </div>

                    {% if event.is_new %}
                      <span class="new-badge">本周新增</span>
                    {% endif %}

                    <h3>
                      <a href="{{ event.link }}" target="_blank">
                        {{ event.title_en }}
                      </a>
                    </h3>

                    <div class="abstract-block">
                      <h4>Details</h4>
                      <p>{{ event.description_en or "No detailed description available. Only title/link was detected." }}</p>
                    </div>

                    <p class="authors">
                      First seen: {{ event.first_seen_display or "Unknown" }}
                      {% if event.last_seen_display %}
                        · Last seen: {{ event.last_seen_display }}
                      {% endif %}
                    </p>

                    <p>
                      <span class="tag conference-tag">{{ event.source_label or "Conference / Seminar" }}</span>
                      <span class="tag">Archive</span>
                      <span class="tag">Score: {{ event.relevance_score or 0 }}</span>
                    </p>
                  </article>
                {% endfor %}
              {% else %}
                <p class="empty">近一年归档中暂无旧条目。当前数据都是最近 {{ new_days }} 天首次抓取到的内容，下一周更新后会自动进入归档。</p>
              {% endif %}
            </div>
          </details>
        {% endfor %}
      {% else %}
        <p class="empty">当前暂无 Tax Conferences / Seminars 数据。</p>
      {% endif %}
    </section>
  </main>
</body>
</html>
"""


def load_json(path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def display_date(value):
    dt = parse_dt(value)
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%d")


def mark_is_new(item):
    if not item.get("first_seen"):
        item["first_seen"] = item.get("fetched_at", "")

    first_seen = parse_dt(item.get("first_seen"))
    if first_seen:
        item["is_new"] = first_seen >= datetime.now(timezone.utc) - timedelta(days=NEW_DAYS)
    else:
        item["is_new"] = False

    return item


def normalize_journal_papers(papers):
    normalized = []

    for paper in papers:
        paper.setdefault("source_category", "journal_article")
        paper.setdefault("section", "Unknown section")

        if "title_en" not in paper:
            paper["title_en"] = paper.get("title", "")

        if "abstract_en" not in paper:
            paper["abstract_en"] = paper.get("abstract", "")

        paper.setdefault("source_info", "")
        paper.setdefault("method", "Unclassified")
        paper.setdefault("tax_related", False)
        paper.setdefault("authors", [])
        paper.setdefault("published", "")
        paper.setdefault("link", "")

        mark_is_new(paper)
        normalized.append(paper)

    return normalized


def normalize_working_papers(papers):
    normalized = []

    for paper in papers:
        paper.setdefault("source_category", "working_paper")
        paper.setdefault("source_name", "Unknown source")
        paper.setdefault("title_en", paper.get("title", ""))
        paper.setdefault("abstract_en", paper.get("abstract", ""))
        paper.setdefault("authors", [])
        paper.setdefault("posted_date", "")
        paper.setdefault("tax_related", True)
        paper.setdefault("link", "")

        mark_is_new(paper)
        normalized.append(paper)

    return normalized


def normalize_conferences(events):
    normalized = []

    for event in events:
        event.setdefault("source_category", "conference")
        event.setdefault("source_name", "Unknown source")
        event.setdefault("source_label", "Conference / Seminar")
        event.setdefault("title_en", "")
        event.setdefault("description_en", "")
        event.setdefault("event_date", "")
        event.setdefault("location", "")
        event.setdefault("link", "")
        event.setdefault("tax_related", True)
        event.setdefault("relevance_score", 0)

        if not event.get("first_seen"):
            event["first_seen"] = event.get("fetched_at", "")

        if not event.get("last_seen"):
            event["last_seen"] = event.get("fetched_at", "")

        event["first_seen_display"] = display_date(event.get("first_seen"))
        event["last_seen_display"] = display_date(event.get("last_seen"))

        mark_is_new(event)

        if event.get("description_en") and len(event["description_en"]) > 500:
            event["description_en"] = event["description_en"][:500] + "..."

        normalized.append(event)

    return normalized


def group_by_journal_and_section(papers):
    grouped = defaultdict(lambda: defaultdict(list))

    for paper in papers:
        journal_id = paper.get("journal_id", "Other")
        section = paper.get("section", "Unknown section")
        grouped[journal_id][section].append(paper)

    return {journal: dict(sections) for journal, sections in grouped.items()}


def count_by_journal(grouped):
    counts = {}

    for journal_id, sections in grouped.items():
        counts[journal_id] = sum(len(papers) for papers in sections.values())

    return counts


def group_by_source(items):
    grouped = defaultdict(list)

    for item in items:
        source_name = item.get("source_name", "Unknown source")
        grouped[source_name].append(item)

    return dict(grouped)


def group_conferences_by_source_with_new_archive(events):
    grouped = {}

    for event in events:
        source_name = event.get("source_name", "Unknown source")

        if source_name not in grouped:
            grouped[source_name] = {
                "new": [],
                "archive": [],
                "total": 0
            }

        if event.get("is_new"):
            grouped[source_name]["new"].append(event)
        else:
            grouped[source_name]["archive"].append(event)

        grouped[source_name]["total"] += 1

    return grouped


def main():
    journal_papers = normalize_journal_papers(load_json(JOURNAL_DATA_PATH))
    working_papers = normalize_working_papers(load_json(WORKING_PAPER_DATA_PATH))
    conferences = normalize_conferences(load_json(CONFERENCE_DATA_PATH))

    journal_papers = sorted(
        journal_papers,
        key=lambda x: x.get("fetched_at", ""),
        reverse=True
    )

    working_papers = sorted(
        working_papers,
        key=lambda x: x.get("fetched_at", ""),
        reverse=True
    )

    conferences = sorted(
        conferences,
        key=lambda x: (
            x.get("relevance_score", 0),
            x.get("first_seen", "")
        ),
        reverse=True
    )

    tax_papers = [p for p in journal_papers if p.get("tax_related")]
    non_tax_papers = [p for p in journal_papers if not p.get("tax_related")]

    tax_grouped = group_by_journal_and_section(tax_papers)
    non_tax_grouped = group_by_journal_and_section(non_tax_papers)

    journal_counts_tax = count_by_journal(tax_grouped)
    journal_counts_non_tax = count_by_journal(non_tax_grouped)

    working_grouped = group_by_source(working_papers)
    conference_by_source = group_conferences_by_source_with_new_archive(conferences)

    template = Template(HTML_TEMPLATE)
    html = template.render(
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        total=len(journal_papers),
        tax_total=len(tax_papers),
        non_tax_total=len(non_tax_papers),
        working_total=len(working_papers),
        conference_total=len(conferences),
        tax_grouped=tax_grouped,
        non_tax_grouped=non_tax_grouped,
        journal_counts_tax=journal_counts_tax,
        journal_counts_non_tax=journal_counts_non_tax,
        working_grouped=working_grouped,
        conference_by_source=conference_by_source,
        journal_order=JOURNAL_ORDER,
        new_days=NEW_DAYS
    )

    SITE_DIR.mkdir(exist_ok=True)
    INDEX_PATH.write_text(html, encoding="utf-8")
    print(f"Built {INDEX_PATH}")


if __name__ == "__main__":
    main()