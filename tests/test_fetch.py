import pytest
from unittest.mock import patch, MagicMock
from fetch import (
    fetch_source, _strip_images, _reddit_embed,
    _extract_reddit_link, _REDDIT_BOILERPLATE, FetchedItem,
)


def test_reddit_embed_returns_iframe_for_reddit_url():
    url = "https://www.reddit.com/r/gaming/comments/abc123/some_post/"
    result = _reddit_embed(url)
    assert result is not None
    assert "redditmedia.com" in result
    assert "embed=true" in result
    assert "<iframe" in result


def test_reddit_embed_strips_trailing_slash_before_appending():
    url = "https://reddit.com/r/pcgaming/comments/xyz789/title"
    result = _reddit_embed(url)
    assert "/?embed=true" in result
    assert "//?embed=true" not in result


def test_reddit_embed_returns_none_for_non_reddit_url():
    assert _reddit_embed("https://example.com/article") is None
    assert _reddit_embed("https://news.ycombinator.com/item?id=123") is None


def test_extract_reddit_link_returns_external_url():
    summary = (
        '<table><tr><td><a href="https://www.youtube.com/watch?v=abc123">'
        '<img src="https://external-preview.redd.it/image.jpg"/></a></td>'
        '<td>submitted by <a href="https://www.reddit.com/user/foo">/u/foo</a>'
        '<a href="https://www.reddit.com/r/indiegaming/comments/x/y/">[link]</a>'
        '<a href="https://www.reddit.com/r/indiegaming/comments/x/y/">[comments]</a>'
        "</td></tr></table>"
    )
    result = _extract_reddit_link(summary)
    assert result == "https://www.youtube.com/watch?v=abc123"


def test_extract_reddit_link_ignores_reddit_internal_urls():
    summary = (
        '<a href="https://www.reddit.com/r/gaming/comments/1/post/">[link]</a>'
        '<a href="https://preview.redd.it/img.jpg">img</a>'
    )
    assert _extract_reddit_link(summary) is None


def test_extract_reddit_link_ignores_image_cdn_and_media_files():
    summary = (
        '<a href="https://pbs.twimg.com/media/abc.jpg">tweet img</a>'
        '<a href="https://example.com/video.mp4">video</a>'
        '<a href="https://www.reddit.com/r/x/comments/y/z/">[link]</a>'
    )
    assert _extract_reddit_link(summary) is None


def test_extract_reddit_link_returns_steam_url():
    summary = (
        '<a href="https://store.steampowered.com/app/12345/GameName/">Steam</a>'
        '<a href="https://www.reddit.com/r/indiegaming/comments/x/y/">[comments]</a>'
    )
    result = _extract_reddit_link(summary)
    assert result == "https://store.steampowered.com/app/12345/GameName/"


def test_reddit_boilerplate_pattern_matches_typical_reddit_description():
    text = "[image →] submitted by /u/johndoe [link] [comments]"
    assert _REDDIT_BOILERPLATE.match(text)


def test_reddit_boilerplate_pattern_does_not_match_real_content():
    text = "Some interesting article about game development and retro consoles."
    assert not _REDDIT_BOILERPLATE.match(text)


def test_strip_images_replaces_with_link():
    html = '<p>Text <img src="https://example.com/img.jpg" alt="x"> end</p>'
    result = _strip_images(html)
    assert "<img" not in result
    assert "[image →]" in result
    assert "https://example.com/img.jpg" in result


def test_strip_images_no_src_removes_tag():
    html = '<p><img alt="no src"> text</p>'
    result = _strip_images(html)
    assert "<img" not in result


def _ok_feed(*entries):
    mock_feed = MagicMock()
    mock_feed.bozo = False
    mock_feed.status = 200
    mock_feed.entries = list(entries)
    return mock_feed


def test_fetch_source_returns_empty_on_feed_failure():
    mock_feed = MagicMock()
    mock_feed.bozo = True
    mock_feed.status = 200
    mock_feed.bozo_exception = Exception("DNS failure")
    mock_feed.entries = []
    with patch("feedparser.parse", return_value=mock_feed):
        items = fetch_source("Test", "https://example.com/rss")
    assert items == []


def test_fetch_source_returns_empty_on_http_error():
    mock_feed = MagicMock()
    mock_feed.bozo = False
    mock_feed.status = 403
    mock_feed.entries = []
    with patch("feedparser.parse", return_value=mock_feed):
        items = fetch_source("Test", "https://example.com/rss")
    assert items == []


def test_fetch_source_skips_comments_only_entries():
    mock_entry = MagicMock()
    mock_entry.get.side_effect = lambda k, d="": {
        "title": "Comments", "link": "https://news.ycombinator.com/item?id=123"
    }.get(k, d)
    mock_entry.content = None
    with patch("feedparser.parse", return_value=_ok_feed(mock_entry)):
        items = fetch_source("Hacker News", "https://news.ycombinator.com/rss")
    assert items == []


def test_fetch_source_skips_entry_without_title():
    mock_entry = MagicMock()
    mock_entry.get.side_effect = lambda k, d="": {"title": "", "link": "https://x.com/1"}.get(k, d)
    mock_entry.content = None
    with patch("feedparser.parse", return_value=_ok_feed(mock_entry)):
        items = fetch_source("Test", "https://example.com/rss")
    assert items == []


def test_fetch_source_skips_entry_without_link():
    mock_entry = MagicMock()
    mock_entry.get.side_effect = lambda k, d="": {"title": "Title", "link": ""}.get(k, d)
    mock_entry.content = None
    with patch("feedparser.parse", return_value=_ok_feed(mock_entry)):
        items = fetch_source("Test", "https://example.com/rss")
    assert items == []


def test_fetch_source_uses_content_encoded_when_long():
    mock_entry = MagicMock()
    long_content = "<p>" + "x" * 400 + "</p>"
    mock_entry.content = [{"value": long_content}]
    mock_entry.get.side_effect = lambda k, d="": {
        "title": "Long Article", "link": "https://example.com/1", "summary": "short"
    }.get(k, d)
    with patch("feedparser.parse", return_value=_ok_feed(mock_entry)):
        items = fetch_source("Test", "https://example.com/rss")
    assert len(items) == 1
    assert items[0].content == long_content


def test_fetch_source_falls_back_to_description():
    mock_entry = MagicMock()
    mock_entry.content = None
    mock_entry.get.side_effect = lambda k, d="": {
        "title": "Article", "link": "https://example.com/1", "summary": "<p>Fallback desc</p>"
    }.get(k, d)
    with patch("feedparser.parse", return_value=_ok_feed(mock_entry)):
        with patch("trafilatura.fetch_url", return_value=None):
            items = fetch_source("Test", "https://example.com/rss")
    assert items[0].content == "<p>Fallback desc</p>"


def test_comic_fetch_embeds_image_from_summary():
    mock_entry = MagicMock()
    mock_entry.content = None
    mock_entry.enclosures = []
    img_url = "https://imgs.xkcd.com/comics/test.png"
    hover = "The punchline nobody asked for."
    mock_entry.get.side_effect = lambda k, d="": {
        "title": "XKCD 123",
        "link": "https://xkcd.com/123/",
        "summary": f'<img src="{img_url}" alt="XKCD 123" title="{hover}" />',
    }.get(k, d)
    with patch("feedparser.parse", return_value=_ok_feed(mock_entry)):
        items = fetch_source("XKCD", "https://xkcd.com/atom.xml", comic=True)
    assert len(items) == 1
    assert items[0].is_comic is True
    content = items[0].content
    assert "<img" in content
    assert img_url in content
    assert hover in content
    assert "comic-hover" in content


def test_comic_fetch_image_without_hover_text():
    mock_entry = MagicMock()
    mock_entry.content = None
    mock_entry.enclosures = []
    img_url = "https://imgs.xkcd.com/comics/test2.png"
    mock_entry.get.side_effect = lambda k, d="": {
        "title": "XKCD 456",
        "link": "https://xkcd.com/456/",
        "summary": f'<img src="{img_url}" />',
    }.get(k, d)
    with patch("feedparser.parse", return_value=_ok_feed(mock_entry)):
        items = fetch_source("XKCD", "https://xkcd.com/atom.xml", comic=True)
    assert "<img" in items[0].content
    assert "comic-hover" not in items[0].content


def test_fetch_source_returns_fetched_item_shape():
    mock_entry = MagicMock()
    mock_entry.content = None
    mock_entry.get.side_effect = lambda k, d="": {
        "title": "Test Article", "link": "https://example.com/test", "summary": "desc"
    }.get(k, d)
    mock_feed = MagicMock()
    mock_feed.entries = [mock_entry]
    with patch("feedparser.parse", return_value=mock_feed):
        with patch("trafilatura.fetch_url", return_value=None):
            items = fetch_source("MyFeed", "https://example.com/rss")
    assert items[0].source == "MyFeed"
    assert items[0].url == "https://example.com/test"
    assert items[0].is_comic is False


def test_reddit_link_post_uses_external_url():
    """Item URL should be the external link, not the Reddit comments page."""
    mock_entry = MagicMock()
    mock_entry.content = None
    reddit_url = "https://www.reddit.com/r/gaming/comments/abc123/some_trailer/"
    youtube_url = "https://www.youtube.com/watch?v=abc123"
    mock_entry.get.side_effect = lambda k, d="": {
        "title": "Some Game Trailer",
        "link": reddit_url,
        "summary": f'<a href="{youtube_url}"><img src="https://preview.redd.it/img.jpg"/></a>'
                   f'submitted by /u/user <a href="{reddit_url}">[link]</a>'
                   f'<a href="{reddit_url}">[comments]</a>',
        "description": "",
    }.get(k, d)
    with patch("feedparser.parse", return_value=_ok_feed(mock_entry)):
        with patch("trafilatura.fetch_url", return_value=None):
            items = fetch_source("r/gaming", "https://www.reddit.com/r/gaming/.rss")
    assert len(items) == 1
    assert items[0].url == youtube_url
    assert "<iframe" in (items[0].content or "")


def test_reddit_self_post_keeps_reddit_url():
    """Self-posts have no external link; URL stays as Reddit comments page."""
    mock_entry = MagicMock()
    mock_entry.content = None
    reddit_url = "https://www.reddit.com/r/gaming/comments/xyz789/discussion/"
    mock_entry.get.side_effect = lambda k, d="": {
        "title": "What's your favourite retro game?",
        "link": reddit_url,
        "summary": (
            "I love old SNES games. submitted by /u/user "
            f'<a href="{reddit_url}">[link]</a>'
            f'<a href="{reddit_url}">[comments]</a>'
        ),
        "description": "",
    }.get(k, d)
    with patch("feedparser.parse", return_value=_ok_feed(mock_entry)):
        items = fetch_source("r/gaming", "https://www.reddit.com/r/gaming/.rss")
    assert len(items) == 1
    assert items[0].url == reddit_url
