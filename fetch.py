import re
import logging
from dataclasses import dataclass
from html import escape as _escape
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
# Domains / path patterns that are not useful article links
_REDDIT_INTERNAL = re.compile(
    r"https?://(?:(?:www\.|old\.)?reddit\.com|"
    r"(?:external-preview|preview|i|v)\.redd\.it|redd\.it)",
    re.IGNORECASE,
)
_MEDIA_EXT = re.compile(r"\.(jpe?g|png|gif|webp|mp4|webm|mov)([?#]|$)", re.IGNORECASE)
_IMAGE_CDN = re.compile(r"https?://pbs\.twimg\.com/", re.IGNORECASE)


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


def _extract_reddit_link(summary_html: str) -> Optional[str]:
    """Return the first non-Reddit, non-media href from a Reddit RSS summary.

    Link posts embed the external URL as the first href; self-posts and
    Reddit-hosted media only have reddit.com hrefs, so this returns None.
    """
    for m in re.finditer(r'href=["\']([^"\']+)["\']', summary_html, re.IGNORECASE):
        url = m.group(1)
        if not url.startswith("http"):
            continue
        if _REDDIT_INTERNAL.match(url):
            continue
        path = url.split("?")[0]
        if _MEDIA_EXT.search(path):
            continue
        if _IMAGE_CDN.match(url):
            continue
        return url
    return None


def _extract_content(entry) -> Optional[str]:
    """Extract article text for non-Reddit items (no embed logic)."""
    url = entry.get("link", "")

    # 1. content:encoded if substantial
    if getattr(entry, "content", None):
        for c in entry.content:
            val = c.get("value", "")
            if len(val) > CONTENT_THRESHOLD:
                return _strip_images(val)

    # 2. trafilatura on linked URL
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


def _fetch_reddit_content(entry, reddit_url: str, external_url: Optional[str]) -> Optional[str]:
    """Build content for a Reddit item: embed + optional article text.

    external_url: the linked article/video (None for self-posts and
    Reddit-hosted media — trafilatura is skipped in that case).
    """
    embed = _reddit_embed(reddit_url)

    # Try to fetch the external article via trafilatura
    body: Optional[str] = None
    if external_url:
        try:
            downloaded = trafilatura.fetch_url(external_url)
            if downloaded:
                plain = trafilatura.extract(downloaded)
                if plain and len(plain) > CONTENT_THRESHOLD:
                    paragraphs = [p.strip() for p in plain.split("\n\n") if p.strip()]
                    body = "<p>" + "</p>\n<p>".join(paragraphs) + "</p>"
        except Exception as e:
            logger.warning("trafilatura failed for %s: %s", external_url, e)

    # Fall back to RSS description/summary
    if not body:
        desc = entry.get("summary") or entry.get("description", "")
        if desc:
            stripped_body = _strip_images(desc)
            visible = re.sub(r"<[^>]+>", "", stripped_body).strip()
            if not _REDDIT_BOILERPLATE.match(visible):
                body = stripped_body

    if embed and body:
        return embed + "\n" + body
    return embed or body


def _extract_comic(entry) -> Optional[str]:
    html = entry.get("summary", "") or entry.get("description", "")
    img_m = re.search(r'<img([^>]+)>', html, re.IGNORECASE)
    if img_m:
        attrs = img_m.group(1)
        src_m = re.search(r'src=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
        title_m = re.search(r'title=["\']([^"\']*)["\']', attrs, re.IGNORECASE)
        alt_m = re.search(r'alt=["\']([^"\']*)["\']', attrs, re.IGNORECASE)
        if src_m:
            src = src_m.group(1)
            alt = alt_m.group(1) if alt_m else ""
            hover = title_m.group(1) if title_m else alt
            img_tag = (
                f'<a href="{_escape(src)}" target="_blank" rel="noopener noreferrer">'
                f'<img src="{_escape(src)}" alt="{_escape(alt)}" '
                f'style="max-width:100%;height:auto;display:block;"></a>'
            )
            if hover:
                return img_tag + f'\n<p class="comic-hover">{_escape(hover)}</p>'
            return img_tag
    for enc in getattr(entry, "enclosures", []):
        if enc.get("type", "").startswith("image/"):
            href = enc.get("href")
            if href:
                return (
                    f'<a href="{_escape(href)}" target="_blank" rel="noopener noreferrer">'
                    f'<img src="{_escape(href)}" alt="" style="max-width:100%;height:auto;display:block;"></a>'
                )
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

        if comic:
            content = _extract_comic(entry)
            display_url = link
        elif _REDDIT_URL.match(link):
            summary_html = entry.get("summary", "") or entry.get("description", "")
            external = _extract_reddit_link(summary_html)
            display_url = external or link
            content = _fetch_reddit_content(entry, reddit_url=link, external_url=external)
        else:
            display_url = link
            content = _extract_content(entry)

        items.append(FetchedItem(title=title, url=display_url, source=name,
                                 content=content, is_comic=comic))
    return items
