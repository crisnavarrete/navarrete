"""Render the publications page from one YAML source of truth.

The preferred input format is documented in ``data/publications/README.md``.
The loader also accepts the former top-level mapping format so existing records
can be migrated incrementally.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Iterable

import yaml

STATUS_ORDER = ("published", "preprint", "working-paper", "in-print")
STATUS_TITLES = {
    "published": "Published",
    "preprint": "Preprints",
    "working-paper": "Working papers",
    "in-print": "In print",
}
STATUS_LABELS = {
    "published": "Published",
    "preprint": "Preprint",
    "working-paper": "Working paper",
    "in-print": "In print",
}
TYPE_LABELS = {
    "article": "Article",
    "educational-resource": "Educational resource",
    "thesis": "Thesis",
    "chapter": "Book chapter",
    "book": "Book",
    "report": "Report",
}
LINK_SPECS = (
    ("published", "Published version", "bi-box-arrow-up-right"),
    ("preprint", "Preprint", "bi-file-earmark-pdf"),
    ("doi", "DOI", "bi-link-45deg"),
    ("code", "Code", "bi-github"),
    ("data", "Data", "bi-database"),
)


@dataclass(frozen=True)
class Publication:
    id: str
    title: str
    authors: tuple[str, ...]
    year: int
    status: str
    kind: str
    venue: str | None
    links: dict[str, str]


@dataclass(frozen=True)
class PublicationData:
    self_author: str
    papers: tuple[Publication, ...]


def _required_text(record: dict[str, Any], field: str, record_id: str) -> str:
    value = str(record.get(field, "")).strip()
    if not value:
        raise ValueError(f"Publication '{record_id}' is missing required field '{field}'.")
    return value


def _normalise_links(record: dict[str, Any]) -> dict[str, str]:
    links = record.get("links") or {}
    if not isinstance(links, dict):
        raise ValueError("The 'links' field must be a mapping.")

    aliases = {
        "published": record.get("published_url"),
        "preprint": record.get("preprint"),
        "code": record.get("github"),
    }
    merged = {**aliases, **links}
    return {
        str(key): str(value).strip()
        for key, value in merged.items()
        if value is not None and str(value).strip()
    }


def _normalise_status(record: dict[str, Any], links: dict[str, str]) -> str:
    raw = str(record.get("status", "")).strip().lower().replace("_", "-")
    aliases = {
        "working": "working-paper",
        "working paper": "working-paper",
        "in-progress": "working-paper",
        "in progress": "working-paper",
        "in print": "in-print",
    }
    status = aliases.get(raw, raw)

    if not status:
        if links.get("published"):
            status = "published"
        elif links.get("preprint"):
            status = "preprint"
        else:
            status = "working-paper"

    if status not in STATUS_ORDER:
        allowed = ", ".join(STATUS_ORDER)
        raise ValueError(f"Unknown publication status '{status}'. Use one of: {allowed}.")

    return status


def _iter_records(raw: Any) -> tuple[str, Iterable[tuple[str, dict[str, Any]]]]:
    if not isinstance(raw, dict):
        raise ValueError("The publication YAML must contain a top-level mapping.")

    if "papers" in raw:
        settings = raw.get("settings") or {}
        if not isinstance(settings, dict):
            raise ValueError("The 'settings' field must be a mapping.")

        self_author = str(settings.get("self_author", "Navarrete, C.")).strip()
        papers = raw.get("papers") or []
        if not isinstance(papers, list):
            raise ValueError("The 'papers' field must be a list.")

        records: list[tuple[str, dict[str, Any]]] = []
        for index, item in enumerate(papers, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"Publication entry {index} must be a mapping.")
            record_id = str(item.get("id", f"paper-{index}")).strip()
            records.append((record_id, item))
        return self_author, records

    records = []
    for record_id, item in raw.items():
        if isinstance(item, dict):
            records.append((str(record_id), item))
    return "Navarrete, C.", records


def load_publications(yaml_path: str | Path) -> PublicationData:
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Publication data not found: {path}")

    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    self_author, records = _iter_records(raw)
    papers: list[Publication] = []
    seen_ids: set[str] = set()

    for record_id, record in records:
        if not record_id:
            raise ValueError("Every publication needs a non-empty 'id'.")
        if record_id in seen_ids:
            raise ValueError(f"Duplicate publication id: '{record_id}'.")
        seen_ids.add(record_id)

        title = _required_text(record, "title", record_id)
        try:
            year = int(record.get("year"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Publication '{record_id}' has an invalid year.") from exc

        raw_authors = record.get("authors", ["self"])
        if not isinstance(raw_authors, list) or not raw_authors:
            raise ValueError(f"Publication '{record_id}' needs a non-empty authors list.")
        authors = tuple(str(author).strip() for author in raw_authors if str(author).strip())

        links = _normalise_links(record)
        status = _normalise_status(record, links)
        kind = str(record.get("type", "article")).strip().lower().replace("_", "-")
        venue = str(record["venue"]).strip() if record.get("venue") else None

        papers.append(
            Publication(
                id=record_id,
                title=title,
                authors=authors,
                year=year,
                status=status,
                kind=kind,
                venue=venue,
                links=links,
            )
        )

    return PublicationData(self_author=self_author, papers=tuple(papers))


def _readable_list(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return " and ".join(items)
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _render_author(author: str, self_author: str) -> str:
    if author.strip().lower() in {"self", "me"}:
        return f'<strong class="author-name">{escape(self_author)}</strong>'
    return escape(author)


def _render_link(url: str | None, label: str, icon: str) -> str:
    if not url:
        return ""
    return (
        f'<a class="pub-link" href="{escape(url, quote=True)}" target="_blank" '
        f'rel="noopener noreferrer"><i class="bi {escape(icon, quote=True)}" '
        f'aria-hidden="true"></i><span>{escape(label)}</span></a>'
    )


def _render_card(paper: Publication, self_author: str) -> str:
    authors = [_render_author(author, self_author) for author in paper.authors]
    tags = [f'<span class="publication-tag">{paper.year}</span>']

    kind_label = TYPE_LABELS.get(paper.kind, paper.kind.replace("-", " ").title())
    if kind_label:
        tags.append(f'<span class="publication-tag">{escape(kind_label)}</span>')
    if paper.venue:
        tags.append(f'<span class="publication-tag">{escape(paper.venue)}</span>')
    if paper.status != "published":
        tags.append(
            f'<span class="publication-tag status">{escape(STATUS_LABELS[paper.status])}</span>'
        )

    actions = [
        _render_link(paper.links.get(key), label, icon)
        for key, label, icon in LINK_SPECS
    ]
    actions_html = "".join(action for action in actions if action)
    if not actions_html:
        actions_html = '<span class="publication-note">Available on request</span>'

    return f"""
<article
  id="{escape(paper.id, quote=True)}"
  class="publication-card type-{escape(paper.kind, quote=True)}"
  data-year="{paper.year}"
  data-status="{escape(paper.status, quote=True)}"
  data-type="{escape(paper.kind, quote=True)}"
>
  <div class="publication-meta">{''.join(tags)}</div>
  <h4 class="publication-title">{escape(paper.title)}</h4>
  <p class="publication-authors">{_readable_list(authors)}</p>
  <div class="publication-actions">{actions_html}</div>
</article>
""".strip()


def _render_section(
    status: str,
    grouped: dict[int, list[Publication]],
    self_author: str,
    year_anchor_status: dict[int, str],
) -> str:
    count = sum(len(items) for items in grouped.values())
    noun = "item" if count == 1 else "items"
    groups: list[str] = []

    for year in sorted(grouped, reverse=True):
        cards = "\n".join(_render_card(item, self_author) for item in grouped[year])
        anchor = f' id="year-{year}"' if year_anchor_status.get(year) == status else ""
        groups.append(
            f"""
<section{anchor} class="publication-year-group" data-publication-year="{year}">
  <h3 class="publication-year">{year}</h3>
  <div class="publication-stack">{cards}</div>
</section>
""".strip()
        )

    return f"""
<section id="{escape(status, quote=True)}" class="publication-section" data-publication-status="{escape(status, quote=True)}">
  <div class="publication-section-header">
    <h2>{escape(STATUS_TITLES[status])}</h2>
    <span class="publication-count">{count} {noun}</span>
  </div>
  {''.join(groups)}
</section>
""".strip()


def render_publications(yaml_path: str | Path) -> str:
    data = load_publications(yaml_path)

    if not data.papers:
        return (
            '<div class="gallery-empty"><h3>No publications yet</h3>'
            '<p>Add records to <code>data/publications/papers.yaml</code>.</p></div>'
        )

    grouped: dict[str, dict[int, list[Publication]]] = {
        status: defaultdict(list) for status in STATUS_ORDER
    }
    years: set[int] = set()

    for paper in data.papers:
        grouped[paper.status][paper.year].append(paper)
        years.add(paper.year)

    status_counts = {
        status: sum(len(items) for items in grouped[status].values())
        for status in STATUS_ORDER
    }
    year_counts = {
        year: sum(len(grouped[status].get(year, [])) for status in STATUS_ORDER)
        for year in years
    }

    # Give each year a single valid HTML anchor, attached to the first status
    # section in which that year appears.
    year_anchor_status: dict[int, str] = {}
    for year in sorted(years, reverse=True):
        for status in STATUS_ORDER:
            if grouped[status].get(year):
                year_anchor_status[year] = status
                break

    sidebar = f"""
<aside class="publications-sidebar" aria-label="Publication navigation">
  <h3>Research</h3>
  <h4>Status</h4>
  <ul>
    {''.join(
        f'<li><a href="#{status}">{escape(STATUS_TITLES[status])} '
        f'<span>({status_counts[status]})</span></a></li>'
        for status in STATUS_ORDER
        if status_counts[status] > 0
    )}
  </ul>
  <h4>Year</h4>
  <ul>
    {''.join(
        f'<li><a href="#year-{year}">{year} '
        f'<span>({year_counts[year]})</span></a></li>'
        for year in sorted(years, reverse=True)
    )}
  </ul>
</aside>
""".strip()

    content = "\n".join(
        _render_section(
            status,
            grouped[status],
            data.self_author,
            year_anchor_status,
        )
        for status in STATUS_ORDER
        if grouped[status]
    )

    return f"""
<div class="publications-layout">
  {sidebar}
  <div class="publications-content">
    {content}
  </div>
</div>
""".strip()


def _main() -> int:
    parser = argparse.ArgumentParser(description="Validate and summarize publication data.")
    parser.add_argument(
        "yaml_path",
        nargs="?",
        default="data/publications/papers.yaml",
        help="Path to papers.yaml",
    )
    args = parser.parse_args()
    data = load_publications(args.yaml_path)
    counts = {status: 0 for status in STATUS_ORDER}
    for paper in data.papers:
        counts[paper.status] += 1
    summary = ", ".join(f"{STATUS_TITLES[key]}: {value}" for key, value in counts.items())
    print(f"Validated {len(data.papers)} publications ({summary}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
