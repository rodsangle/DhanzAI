"""Main-content extraction from HTML: title, readable text and metadata."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from bs4 import BeautifulSoup, Tag

from dhanz_knowledge.types import Page

_DROP = ["script", "style", "noscript", "template", "svg", "canvas", "iframe", "form", "button", "input", "select"]
_BOILERPLATE = ["nav", "header", "footer", "aside"]
_BOILERPLATE_HINT = re.compile(
    r"(^|[-_ ])(nav|menu|footer|header|sidebar|cookie|consent|banner|advert|ads?|promo|share|social|"
    r"related|comments?|newsletter|subscribe|breadcrumb)([-_ ]|$)",
    re.IGNORECASE,
)
_BLOCKS = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote", "td", "th", "dt", "dd", "figcaption"}
_WS = re.compile(r"[ \t\r\f\v]+")


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    for candidate in (value, value.replace("Z", "+00:00")):
        try:
            dt = datetime.fromisoformat(candidate)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            continue
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", value)
    if m:
        try:
            return datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=UTC)
        except ValueError:
            return None
    return None


def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if isinstance(tag, Tag) and tag.get("content"):
            return str(tag["content"]).strip()
    return None


def _json_ld(soup: BeautifulSoup) -> dict:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        for item in items:
            if isinstance(item, dict) and (item.get("datePublished") or item.get("headline")):
                return item
    return {}


def _text_of(root: Tag) -> str:
    lines: list[str] = []
    for el in root.find_all(_BLOCKS):
        # Skip containers whose text is captured through a nested block (e.g. <li><p>..</p></li>).
        if el.find(_BLOCKS):
            continue
        text = _WS.sub(" ", el.get_text(" ", strip=True)).strip()
        if not text:
            continue
        if el.name and el.name.startswith("h"):
            text = "## " + text
        elif el.name == "li":
            text = "- " + text
        lines.append(text)
    if not lines:
        lines = [line.strip() for line in root.get_text("\n").splitlines() if line.strip()]
    # Remove exact duplicate lines (menus repeated in the body etc.) while keeping order.
    seen: set[str] = set()
    out = []
    for line in lines:
        if line not in seen:
            seen.add(line)
            out.append(line)
    return "\n".join(out)


def _main_root(soup: BeautifulSoup) -> Tag:
    for selector in ("article", "main", "[role=main]", "#content", ".content", ".post", ".article"):
        candidates = soup.select(selector)
        if candidates:
            return max(candidates, key=lambda t: len(t.get_text(" ", strip=True)))
    return soup.body or soup


def extract_page(html: str, url: str, *, is_html: bool = True) -> Page:
    if not is_html:
        text = "\n".join(line.rstrip() for line in html.splitlines()).strip()
        return Page(url=url, title=url.rsplit("/", 1)[-1] or url, text=text)

    soup = BeautifulSoup(html, "lxml")
    ld = _json_ld(soup)
    title = (
        _meta(soup, "og:title", "twitter:title")
        or (soup.title.string.strip() if soup.title and soup.title.string else None)
        or (ld.get("headline") if isinstance(ld.get("headline"), str) else None)
        or url
    )
    published = parse_date(
        _meta(soup, "article:published_time", "datePublished", "pubdate", "date", "dc.date")
        or (ld.get("datePublished") if isinstance(ld.get("datePublished"), str) else None)
        or (soup.find("time").get("datetime") if isinstance(soup.find("time"), Tag) else None)
    )
    author = _meta(soup, "author", "article:author")
    if not author and isinstance(ld.get("author"), dict):
        author = ld["author"].get("name")
    site_name = _meta(soup, "og:site_name", "application-name")
    lang = soup.html.get("lang") if soup.html and soup.html.get("lang") else None

    for tag in soup(_DROP):
        tag.decompose()
    for tag in soup(_BOILERPLATE):
        tag.decompose()
    for tag in soup.find_all(True):
        if tag.decomposed or tag.name in ("html", "body", "main", "article"):
            continue
        hint = " ".join([*(tag.get("class") or []), str(tag.get("id") or "")])
        # Only small blocks: a page wrapper with class "has-sidebar" must not take the article with it.
        if hint.strip() and _BOILERPLATE_HINT.search(hint) and len(tag.get_text(" ", strip=True)) < 1500:
            tag.decompose()

    text = _text_of(_main_root(soup))
    return Page(
        url=url,
        title=_WS.sub(" ", str(title)).strip()[:300],
        text=text,
        site_name=site_name,
        author=author if isinstance(author, str) else None,
        published_at=published,
        language=str(lang) if lang else None,
    )
