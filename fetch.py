import re
import logging
from dataclasses import dataclass
from typing import Optional

import feedparser
import trafilatura

logger = logging.getLogger(__name__)

CONTENT_THRESHOLD = 300
_UA = "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"
_REDDIT_URL = re.compile(r"^https://(?:www\.)?reddit\.com/r/\w+/comments/\w+")
_REDDIT_BOILERPLATE = re.compile(
    r"^\s*(?:\[image\s*→\]\s*)?submitted by\b.*\[link\].*\[comments\]",
    re.DOTALL | re.IGNORECASE,
)


@dataclass
class FetchedItem:
    title: str
    url: str
    source: str
    content: Optional[str]
    is_comic: bool


def _strip_images(html: str) -> str:
    def replace_img(m):
        src = re.search(r'src=["\']([^"\']+)["\']', m.group(0))
        return f'<a href="{src.group(1)}">[image →]</a>' if src else ""

    return re.sub(r"<img[^>]+>", replace_img, html, flags=re.IGNORECASE)


def _reddit_embed(url: str) -> Optional[str]:
    if not _REDDIT_URL.match(url):
        return None
    embed_url = re.sub(r"^https://(?:www\.)?reddit\.com", "https://www.redditmedia.com", url)
    embed_url = embed_url.rstrip("/") + "/?embed=true"
    return (
        f'<iframe src="{embed_url}" style="border:none;width:100%;height:500px" '
        f'scrolling="no" allowfullscreen></iframe>'
    )


def _extract_content(entry) -> Optional[str]:
    url = entry.get("link", "")
    embed = _reddit_embed(url)

    # 1. content:encoded if substantial
    if getattr(entry, "content", None):
        for c in entry.content:
            val = c.get("value", "")
            if len(val) > CONTENT_THRESHOLD:
                body = _strip_images(val)
                return (embed + "\n" + body) if embed else body

    # 2. trafilatura on linked URL
    if url:
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                plain = trafilatura.extract(downloaded)
                if plain and len(plain) > CONTENT_THRESHOLD:
                    paragraphs = [p.strip() for p in plain.split("\n\n") if p.strip()]
                    body = "<p>" + "</p>\n<p>".join(paragraphs) + "</p>"
                    return (embed + "\n" + body) if embed else body
        except Exception as e:
            logger.warning("trafilatura failed for %s: %s", url, e)

    # 3. description/summary fallback
    desc = entry.get("summary") or entry.get("description", "")
    if desc:
        body = _strip_images(desc)
        visible = re.sub(r"<[^>]+>", "", body).strip()
        if embed and _REDDIT_BOILERPLATE.match(visible):
            return embed  # boilerplate adds nothing; embed is enough
        return (embed + "\n" + body) if embed else body

    return embed  # embed alone if no text content


def _extract_comic(entry) -> Optional[str]:
    html = entry.get("summary", "") or entry.get("description", "")
    src = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if src:
        return f'<a href="{src.group(1)}">[image →]</a>'
    for enc in getattr(entry, "enclosures", []):
        if enc.get("type", "").startswith("image/"):
            href = enc.get("href")
            if href:
                return f'<a href="{href}">[image →]</a>'
    return None


def fetch_source(name: str, url: str, comic: bool = False) -> list[FetchedItem]:
    feed = feedparser.parse(url, agent=_UA)
    status = getattr(feed, "status", 200)
    if isinstance(status, int) and status >= 400:
        logger.warning("Feed %s returned HTTP %s", name, status)
        return []
    if feed.bozo and not feed.entries:
        logger.warning("Failed to parse feed %s: %s", name, feed.bozo_exception)
        return []

    items = []
    for entry in feed.entries:
        title = entry.get("title", "").strip()
        link = entry.get("link", "")
        if not title or not link:
            continue
        if title.lower() == "comments":
            continue
        content = _extract_comic(entry) if comic else _extract_content(entry)
        items.append(FetchedItem(title=title, url=link, source=name,
                                 content=content, is_comic=comic))
    return items
