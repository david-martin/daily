import re
import logging
from dataclasses import dataclass
from typing import Optional

import feedparser
import trafilatura

logger = logging.getLogger(__name__)

CONTENT_THRESHOLD = 300


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


def _extract_content(entry) -> Optional[str]:
    # 1. content:encoded if substantial
    if getattr(entry, "content", None):
        for c in entry.content:
            val = c.get("value", "")
            if len(val) > CONTENT_THRESHOLD:
                return _strip_images(val)

    # 2. trafilatura on linked URL
    url = entry.get("link")
    if url:
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                plain = trafilatura.extract(downloaded)
                if plain and len(plain) > CONTENT_THRESHOLD:
                    paragraphs = [p.strip() for p in plain.split("\n\n") if p.strip()]
                    return "<p>" + "</p>\n<p>".join(paragraphs) + "</p>"
        except Exception as e:
            logger.warning("trafilatura failed for %s: %s", url, e)

    # 3. description/summary fallback
    desc = entry.get("summary") or entry.get("description", "")
    if desc:
        return _strip_images(desc)

    return None


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
    feed = feedparser.parse(url)
    if feed.bozo and not feed.entries:
        logger.warning("Failed to parse feed %s: %s", name, feed.bozo_exception)
        return []

    items = []
    for entry in feed.entries:
        title = entry.get("title", "").strip()
        link = entry.get("link", "")
        if not title or not link:
            continue
        content = _extract_comic(entry) if comic else _extract_content(entry)
        items.append(FetchedItem(title=title, url=link, source=name,
                                 content=content, is_comic=comic))
    return items
