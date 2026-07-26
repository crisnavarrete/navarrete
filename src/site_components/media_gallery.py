from __future__ import annotations

import csv
import re
import time
import unicodedata
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Iterable
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _read_csv(path: Path) -> list[dict[str, str]]:
    """Read a UTF-8 CSV file into a list of dictionaries."""
    if not path.exists() or path.stat().st_size == 0:
        return []

    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _first(row: dict[str, str], *names: str) -> str:
    """Return the first non-empty value among possible column names."""
    lower = {
        str(key).strip().lower(): (value or "")
        for key, value in row.items()
    }

    for name in names:
        value = lower.get(name.lower(), "").strip()
        if value:
            return value

    return ""


def _parse_date(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None

    formats = (
        "%Y/%m/%d",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S",
    )

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue

    return None


def _clean_isbn(value: str) -> str:
    return re.sub(r"[^0-9Xx]", "", value or "").upper()


def _initials(title: str) -> str:
    words = re.findall(r"[\wÀ-ÿ]+", title, flags=re.UNICODE)

    if not words:
        return "•"

    if len(words) == 1:
        return words[0][:2].upper()

    return (words[0][0] + words[1][0]).upper()


def _rating(value: str) -> float | None:
    try:
        rating = float(value)
    except (TypeError, ValueError):
        return None

    if rating <= 0:
        return None

    return min(rating, 5.0)


def _review(value: str) -> str:
    return (value or "").strip()


def _render_review(review: str) -> str:
    """Goodreads review block. Letterboxd reviews live in blog posts."""
    safe_review = escape(review).replace("\n", "<br>")

    return (
        '<details class="media-review">'
        '<summary>My review</summary>'
        f'<div class="media-review-body">{safe_review}</div>'
        "</details>"
    )


def _toolbar(years: Iterable[str]) -> str:
    unique = sorted(
        {year for year in years if year and year != "Undated"},
        reverse=True,
    )

    buttons = [
        '<button class="gallery-filter is-active" '
        'type="button" data-filter="all" aria-pressed="true">All</button>'
    ]

    buttons.extend(
        '<button class="gallery-filter" '
        f'type="button" data-filter="{escape(year, quote=True)}" '
        f'aria-pressed="false">{escape(year)}</button>'
        for year in unique
    )

    return (
        '<div class="gallery-toolbar" data-gallery-filter '
        'aria-label="Filter gallery by year">'
        f'{"".join(buttons)}'
        "</div>"
    )


def _cover_markup(url: str, title: str) -> str:
    placeholder = (
        '<div class="media-cover-placeholder" aria-hidden="true">'
        f"{escape(_initials(title))}"
        "</div>"
    )

    if not url:
        return placeholder

    safe_url = escape(url, quote=True)
    safe_alt = escape(f"Cover of {title}", quote=True)

    return (
        f'<img src="{safe_url}" alt="{safe_alt}" loading="lazy" '
        'decoding="async" onerror="this.remove()">'
        f"{placeholder}"
    )


def _empty_state(title: str, instructions: str) -> str:
    return f"""
<div class="gallery-empty">
  <h3>{escape(title)}</h3>
  <p>{instructions}</p>
</div>
""".strip()


# ---------------------------------------------------------------------------
# Goodreads gallery
# ---------------------------------------------------------------------------


def render_goodreads(csv_path: str | Path) -> str:
    path = Path(csv_path)
    rows = _read_csv(path)

    if not rows:
        return _empty_state(
            "Your Goodreads gallery is ready for data",
            "Export your Goodreads library, save the CSV as "
            "<code>data/reading/goodreads_library_export.csv</code>, "
            "and render the site again.",
        )

    books: list[dict[str, str | float | None | datetime]] = []

    for row in rows:
        shelf = _first(row, "Exclusive Shelf", "Shelf")
        date_read = _parse_date(_first(row, "Date Read", "Read Date"))

        if (
            shelf
            and shelf.lower() not in {"read", "currently-reading"}
            and not date_read
        ):
            continue

        title = _first(row, "Title") or "Untitled"
        author = _first(row, "Author") or "Unknown author"
        book_id = _first(row, "Book Id", "Book ID", "ID")
        isbn = _clean_isbn(_first(row, "ISBN13", "ISBN"))

        cover_url = (
            "https://covers.openlibrary.org/b/isbn/"
            f"{quote(isbn)}-L.jpg?default=false"
            if isbn
            else ""
        )

        link = _first(row, "URL", "Link")
        if not link and book_id:
            link = "https://www.goodreads.com/book/show/" f"{quote(book_id)}"

        books.append(
            {
                "title": title,
                "author": author,
                "link": link,
                "cover": cover_url,
                "rating": _rating(_first(row, "My Rating", "Rating")),
                "date": date_read,
                "year": str(date_read.year) if date_read else "Undated",
                "pages": _first(row, "Number of Pages", "Pages"),
                "review": _review(
                    _first(row, "My Review", "Review", "Comments")
                ),
            }
        )

    books.sort(
        key=lambda item: item["date"] or datetime.min,
        reverse=True,
    )

    if not books:
        return _empty_state(
            "No read books found",
            "Check that your Goodreads export contains records on the "
            "<code>read</code> shelf or records with a reading date.",
        )

    cards: list[str] = []

    for book in books:
        title = str(book["title"])
        author = str(book["author"])
        year = str(book["year"])
        link = str(book["link"] or "")

        title_html = escape(title)
        if link:
            title_html = (
                f'<a href="{escape(link, quote=True)}" target="_blank" '
                f'rel="noopener noreferrer">{title_html}</a>'
            )

        badges: list[str] = []

        rating = book["rating"]
        if isinstance(rating, float):
            badges.append(
                '<span class="media-badge rating" '
                f'aria-label="Rated {rating:g} out of 5">'
                f"★ {rating:g}</span>"
            )

        if year != "Undated":
            badges.append(
                '<span class="media-badge">'
                '<i class="bi bi-calendar3" aria-hidden="true"></i>'
                f"{escape(year)}</span>"
            )

        pages = str(book["pages"] or "").strip()
        if pages:
            badges.append(
                f'<span class="media-badge">{escape(pages)} pp.</span>'
            )

        review_text = str(book.get("review") or "").strip()
        review_html = _render_review(review_text) if review_text else ""

        cards.append(
            f"""
<article class="media-card" data-gallery-item data-year="{escape(year, quote=True)}">
  <div class="media-cover">{_cover_markup(str(book['cover'] or ''), title)}</div>
  <div class="media-body">
    <h3 class="media-title">{title_html}</h3>
    <p class="media-creator">{escape(author)}</p>
    <div class="media-details">{''.join(badges)}</div>
    {review_html}
  </div>
</article>
""".strip()
        )

    return (
        '<section class="gallery-section">'
        f'{_toolbar(str(book["year"]) for book in books)}'
        f'<div class="media-grid">{"".join(cards)}</div>'
        "</section>"
    )


# ---------------------------------------------------------------------------
# Blog post discovery and film-title matching
# ---------------------------------------------------------------------------


_FRONT_MATTER_RE = re.compile(
    r"\A---\s*\r?\n(?P<yaml>.*?)\r?\n---\s*(?:\r?\n|$)",
    flags=re.DOTALL,
)


def _front_matter_scalar(yaml_text: str, key: str) -> str:
    """Read a simple one-line scalar from Quarto YAML front matter."""
    pattern = re.compile(
        rf"^\s*{re.escape(key)}\s*:\s*(.*?)\s*$",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    match = pattern.search(yaml_text)

    if not match:
        return ""

    value = match.group(1).strip()

    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]

    return value.strip()


def _normalise_match_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    words = re.findall(r"[a-z0-9]+", without_accents.lower())
    return " ".join(words)


def _post_href(path: Path, project_root: Path) -> str:
    """Convert a source .qmd path to its expected Quarto .html URL."""
    try:
        relative = path.resolve().relative_to(project_root.resolve())
    except ValueError:
        relative = path

    return relative.with_suffix(".html").as_posix()


def _discover_blog_posts(
    posts_dir: str | Path = "posts",
) -> list[dict[str, str]]:
    posts_root = Path(posts_dir)

    if not posts_root.exists():
        return []

    posts: list[dict[str, str]] = []
    project_root = posts_root.parent if posts_root.name == "posts" else Path.cwd()

    for source_path in sorted(posts_root.rglob("*.qmd")):
        try:
            text = source_path.read_text(encoding="utf-8-sig")
        except OSError:
            continue

        front_matter = _FRONT_MATTER_RE.match(text)
        if not front_matter:
            continue

        yaml_text = front_matter.group("yaml")
        title = _front_matter_scalar(yaml_text, "title")

        if not title:
            continue

        draft = _front_matter_scalar(yaml_text, "draft").lower()
        if draft in {"true", "yes", "1"}:
            continue

        # Optional exact override. Title matching still works without this.
        film = (
            _front_matter_scalar(yaml_text, "film")
            or _front_matter_scalar(yaml_text, "movie")
            or _front_matter_scalar(yaml_text, "letterboxd-film")
        )

        posts.append(
            {
                "title": title,
                "title_normalised": _normalise_match_text(title),
                "film": film,
                "film_normalised": _normalise_match_text(film),
                "href": _post_href(source_path, project_root),
            }
        )

    return posts


def _match_blog_review(
    film_title: str,
    posts: list[dict[str, str]],
) -> dict[str, str] | None:
    """Match a rated film to a blog post by metadata or post title."""
    film_normalised = _normalise_match_text(film_title)

    if not film_normalised:
        return None

    film_tokens = film_normalised.split()
    candidates: list[tuple[int, int, dict[str, str]]] = []

    for post in posts:
        post_title = post["title_normalised"]
        explicit_film = post["film_normalised"]
        score = 0

        if explicit_film and explicit_film == film_normalised:
            score = 100
        elif post_title == film_normalised:
            score = 90
        elif len(film_normalised) >= 4 and (
            f" {film_normalised} " in f" {post_title} "
        ):
            # Example: Hamnet -> Sobre Hamnet
            score = 80
        elif len(film_tokens) >= 2 and all(
            token in post_title.split() for token in film_tokens
        ):
            score = 60

        if score:
            # Prefer the closest/shortest matching title when scores tie.
            distance = abs(len(post_title) - len(film_normalised))
            candidates.append((score, -distance, post))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2]


def _render_blog_review_link(post: dict[str, str]) -> str:
    href = escape(post["href"], quote=True)
    post_title = escape(post["title"], quote=True)

    return (
        '<a class="media-blog-review" '
        f'href="{href}" title="{post_title}">'
        '<i class="bi bi-pencil-square" aria-hidden="true"></i>'
        "Read my review"
        "</a>"
    )


# ---------------------------------------------------------------------------
# Letterboxd image cache
# ---------------------------------------------------------------------------


def _safe_slug(url: str, fallback: str = "film") -> str:
    path_name = Path(urlparse(url).path).name or fallback
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", path_name).strip("-")
    return slug or fallback


def _extract_poster_url(page_url: str, html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    selectors = (
        ("meta", {"property": "og:image"}),
        ("meta", {"name": "twitter:image"}),
        ("meta", {"property": "twitter:image"}),
    )

    for tag_name, attrs in selectors:
        tag = soup.find(tag_name, attrs=attrs)
        if tag:
            content = str(tag.get("content") or "").strip()
            if content:
                return urljoin(page_url, content)

    return ""


def _cache_letterboxd_posters(
    rows: list[dict[str, str]],
    poster_dir: str | Path = "assets/images/letterboxd/posters",
    request_delay: float = 0.5,
) -> dict[str, str]:
    destination = Path(poster_dir)
    destination.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/137.0 Safari/537.36"
        ),
        "Accept-Language": "en-GB,en;q=0.9",
    }

    poster_map: dict[str, str] = {}

    with requests.Session() as session:
        session.headers.update(headers)

        for index, row in enumerate(rows, start=1):
            page_url = _first(row, "Letterboxd URI", "URI", "URL")
            title = _first(row, "Name", "Title") or f"film-{index}"

            if not page_url:
                continue

            slug = _safe_slug(page_url, fallback=_safe_slug(title))
            outfile = destination / f"{slug}.jpg"

            if outfile.exists() and outfile.stat().st_size > 0:
                poster_map[page_url] = outfile.as_posix()
                continue

            try:
                page_response = session.get(page_url, timeout=20)
                page_response.raise_for_status()

                poster_url = _extract_poster_url(
                    page_response.url,
                    page_response.text,
                )

                if not poster_url:
                    print(f"No poster metadata found: {page_url}")
                    continue

                image_response = session.get(poster_url, timeout=20)
                image_response.raise_for_status()

                content_type = image_response.headers.get(
                    "Content-Type",
                    "",
                ).lower()

                if content_type and not content_type.startswith("image/"):
                    print(
                        f"Skipped non-image response for {title}: "
                        f"{content_type}"
                    )
                    continue

                outfile.write_bytes(image_response.content)

                if outfile.stat().st_size == 0:
                    outfile.unlink(missing_ok=True)
                    continue

                poster_map[page_url] = outfile.as_posix()
                print(f"Downloaded image: {title}")

                time.sleep(max(request_delay, 0.0))

            except requests.RequestException as error:
                outfile.unlink(missing_ok=True)
                print(f"Image download failed for {page_url}: {error}")
            except OSError as error:
                outfile.unlink(missing_ok=True)
                print(f"Could not save image for {title}: {error}")

    return poster_map


# ---------------------------------------------------------------------------
# Letterboxd gallery: rated films + links to matching blog reviews
# ---------------------------------------------------------------------------


def render_letterboxd(
    ratings_path: str | Path,
    posts_dir: str | Path = "posts",
    poster_dir: str | Path = "assets/images/letterboxd/posters",
    request_delay: float = 0.5,
) -> str:
    """
    Render only films contained in ratings.csv.

    A blog review link is added when the film title appears in a post title.
    For example, the film "Hamnet" matches a post titled "Sobre Hamnet".
    An optional `film:` field in a post's YAML provides an exact override.
    """
    rating_rows = _read_csv(Path(ratings_path))

    if not rating_rows:
        return _empty_state(
            "Your Letterboxd gallery is ready for data",
            "Export <code>ratings.csv</code> from Letterboxd and save it as "
            "<code>data/films/letterboxd/ratings.csv</code>.",
        )

    posts = _discover_blog_posts(posts_dir)

    poster_cache = _cache_letterboxd_posters(
        rating_rows,
        poster_dir=poster_dir,
        request_delay=request_delay,
    )

    films: list[dict[str, str | float | None | datetime | dict[str, str]]] = []

    for rating_row in rating_rows:
        title = _first(rating_row, "Name", "Title") or "Untitled"
        film_year = _first(rating_row, "Year", "Release Year")
        link = _first(rating_row, "Letterboxd URI", "URI", "URL")
        rated_date = _parse_date(
            _first(rating_row, "Date", "Watched Date", "Logged Date")
        )
        gallery_year = (
            str(rated_date.year)
            if rated_date
            else (film_year or "Undated")
        )
        rating = _rating(_first(rating_row, "Rating"))
        blog_post = _match_blog_review(title, posts)

        films.append(
            {
                "title": title,
                "film_year": film_year,
                "link": link,
                "poster": poster_cache.get(link, ""),
                "rating": rating,
                "watched": rated_date,
                "year": gallery_year,
                "blog_post": blog_post or {},
            }
        )

    films.sort(
        key=lambda item: item["watched"] or datetime.min,
        reverse=True,
    )

    cards: list[str] = []

    for film in films:
        title = str(film["title"])
        letterboxd_link = str(film["link"] or "")
        year = str(film["year"])

        title_html = escape(title)
        if letterboxd_link:
            title_html = (
                f'<a href="{escape(letterboxd_link, quote=True)}" '
                f'target="_blank" rel="noopener noreferrer">'
                f"{title_html}</a>"
            )

        badges: list[str] = []

        rating = film["rating"]
        if isinstance(rating, float):
            badges.append(
                '<span class="media-badge rating" '
                f'aria-label="Rated {rating:g} out of 5">'
                f"★ {rating:g}</span>"
            )

        watched = film["watched"]
        if isinstance(watched, datetime):
            badges.append(
                '<span class="media-badge">'
                '<i class="bi bi-calendar3" aria-hidden="true"></i>'
                f'{watched.strftime("%b %Y")}</span>'
            )

        release = str(film["film_year"] or "").strip()
        creator = f"Film · {release}" if release else "Film"

        blog_post = film.get("blog_post")
        blog_link_html = (
            _render_blog_review_link(blog_post)
            if isinstance(blog_post, dict) and blog_post
            else ""
        )

        cards.append(
            f"""
<article class="media-card" data-gallery-item data-year="{escape(year, quote=True)}">
  <div class="media-cover">{_cover_markup(str(film['poster'] or ''), title)}</div>
  <div class="media-body">
    <h3 class="media-title">{title_html}</h3>
    <p class="media-creator">{escape(creator)}</p>
    <div class="media-details">{''.join(badges)}</div>
    {blog_link_html}
  </div>
</article>
""".strip()
        )

    return (
        '<section class="gallery-section">'
        f'{_toolbar(str(film["year"]) for film in films)}'
        f'<div class="media-grid">{"".join(cards)}</div>'
        "</section>"
    )
