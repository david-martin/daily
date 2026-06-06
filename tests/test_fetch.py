import pytest
from unittest.mock import patch, MagicMock
from fetch import fetch_source, _strip_images, FetchedItem


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


def test_fetch_source_returns_empty_on_feed_failure():
    with patch("feedparser.parse", side_effect=Exception("timeout")):
        items = fetch_source("Test", "https://example.com/rss")
    assert items == []


def test_fetch_source_skips_entry_without_title():
    mock_entry = MagicMock()
    mock_entry.get.side_effect = lambda k, d="": {"title": "", "link": "https://x.com/1"}.get(k, d)
    mock_entry.content = None
    mock_feed = MagicMock()
    mock_feed.entries = [mock_entry]
    with patch("feedparser.parse", return_value=mock_feed):
        items = fetch_source("Test", "https://example.com/rss")
    assert items == []


def test_fetch_source_skips_entry_without_link():
    mock_entry = MagicMock()
    mock_entry.get.side_effect = lambda k, d="": {"title": "Title", "link": ""}.get(k, d)
    mock_entry.content = None
    mock_feed = MagicMock()
    mock_feed.entries = [mock_entry]
    with patch("feedparser.parse", return_value=mock_feed):
        items = fetch_source("Test", "https://example.com/rss")
    assert items == []


def test_fetch_source_uses_content_encoded_when_long():
    mock_entry = MagicMock()
    long_content = "<p>" + "x" * 400 + "</p>"
    mock_entry.content = [{"value": long_content}]
    mock_entry.get.side_effect = lambda k, d="": {
        "title": "Long Article", "link": "https://example.com/1", "summary": "short"
    }.get(k, d)
    mock_feed = MagicMock()
    mock_feed.entries = [mock_entry]
    with patch("feedparser.parse", return_value=mock_feed):
        items = fetch_source("Test", "https://example.com/rss")
    assert len(items) == 1
    assert items[0].content == long_content


def test_fetch_source_falls_back_to_description():
    mock_entry = MagicMock()
    mock_entry.content = None
    mock_entry.get.side_effect = lambda k, d="": {
        "title": "Article", "link": "https://example.com/1", "summary": "<p>Fallback desc</p>"
    }.get(k, d)
    mock_feed = MagicMock()
    mock_feed.entries = [mock_entry]
    with patch("feedparser.parse", return_value=mock_feed):
        with patch("trafilatura.fetch_url", return_value=None):
            items = fetch_source("Test", "https://example.com/rss")
    assert items[0].content == "<p>Fallback desc</p>"


def test_comic_fetch_extracts_image_from_summary():
    mock_entry = MagicMock()
    mock_entry.content = None
    mock_entry.enclosures = []
    img_url = "https://imgs.xkcd.com/comics/test.png"
    mock_entry.get.side_effect = lambda k, d="": {
        "title": "XKCD 123",
        "link": "https://xkcd.com/123/",
        "summary": f'<img src="{img_url}" />',
    }.get(k, d)
    mock_feed = MagicMock()
    mock_feed.entries = [mock_entry]
    with patch("feedparser.parse", return_value=mock_feed):
        items = fetch_source("XKCD", "https://xkcd.com/atom.xml", comic=True)
    assert len(items) == 1
    assert items[0].is_comic is True
    assert "[image →]" in items[0].content
    assert img_url in items[0].content


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
