import pytest
import sqlite3
from db import Item, init, comic_seen, store_briefing, get_items_for_date, get_briefing_dates, prev_briefing_date


@pytest.fixture
def db_path(tmp_path):
    p = str(tmp_path / "test.db")
    init(p)
    return p


def test_init_creates_tables(db_path):
    with sqlite3.connect(db_path) as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    assert "briefings" in tables
    assert "items" in tables


def test_store_and_retrieve_item(db_path):
    items = [Item(title="Test", url="https://example.com/1", source="Feed",
                  content="<p>Hi</p>", score=7.5, is_comic=False, rank=1)]
    store_briefing(db_path, "2026-06-06", "2026-06-06T07:00:00Z", items)
    result = get_items_for_date(db_path, "2026-06-06")
    assert len(result) == 1
    assert result[0].title == "Test"
    assert result[0].score == 7.5


def test_comic_seen_false_for_new(db_path):
    assert comic_seen(db_path, "https://xkcd.com/123/") is False


def test_comic_seen_true_after_store(db_path):
    items = [Item(title="XKCD 1", url="https://xkcd.com/123/", source="XKCD",
                  content='<img src="x">', score=None, is_comic=True, rank=None)]
    store_briefing(db_path, "2026-06-05", "2026-06-05T07:00:00Z", items)
    assert comic_seen(db_path, "https://xkcd.com/123/") is True


def test_comic_seen_ignores_same_day(db_path):
    items = [Item(title="XKCD", url="https://xkcd.com/1/", source="XKCD",
                  content='<img src="x">', score=None, is_comic=True, rank=None)]
    store_briefing(db_path, "2026-06-06", "2026-06-06T07:00:00Z", items)
    # Same day should not count as "seen before"
    assert comic_seen(db_path, "https://xkcd.com/1/", before_date="2026-06-06") is False
    # A later date should see it as previously shown
    assert comic_seen(db_path, "https://xkcd.com/1/", before_date="2026-06-07") is True


def test_store_is_idempotent(db_path):
    items = [Item(title="T", url="https://example.com/1", source="S",
                  content=None, score=5.0, is_comic=False, rank=1)]
    store_briefing(db_path, "2026-06-06", "2026-06-06T07:00:00Z", items)
    store_briefing(db_path, "2026-06-06", "2026-06-06T07:00:01Z", items)
    assert len(get_items_for_date(db_path, "2026-06-06")) == 1


def test_get_briefing_dates_reverse_order(db_path):
    for d in ["2026-06-04", "2026-06-06", "2026-06-05"]:
        store_briefing(db_path, d, f"{d}T07:00:00Z", [])
    assert get_briefing_dates(db_path) == ["2026-06-06", "2026-06-05", "2026-06-04"]


def test_prev_briefing_date(db_path):
    for d in ["2026-06-04", "2026-06-05", "2026-06-06"]:
        store_briefing(db_path, d, f"{d}T07:00:00Z", [])
    assert prev_briefing_date(db_path, "2026-06-06") == "2026-06-05"
    assert prev_briefing_date(db_path, "2026-06-04") is None


def test_get_items_for_date_orders_comics_last(db_path):
    items = [
        Item(title="Comic", url="https://xkcd.com/1/", source="XKCD",
             content="<a>[image →]</a>", score=None, is_comic=True, rank=None),
        Item(title="Article A", url="https://example.com/a", source="Feed",
             content="<p>content</p>", score=9.0, is_comic=False, rank=1),
        Item(title="Article B", url="https://example.com/b", source="Feed",
             content="<p>content</p>", score=7.0, is_comic=False, rank=2),
    ]
    store_briefing(db_path, "2026-06-06", "2026-06-06T07:00:00Z", items)
    result = get_items_for_date(db_path, "2026-06-06")
    assert result[0].title == "Article A"
    assert result[1].title == "Article B"
    assert result[2].title == "Comic"
    assert result[2].is_comic is True


def test_comic_seen_does_not_match_non_comic(db_path):
    items = [Item(title="Article", url="https://example.com/1", source="Feed",
                  content="<p>text</p>", score=7.0, is_comic=False, rank=1)]
    store_briefing(db_path, "2026-06-06", "2026-06-06T07:00:00Z", items)
    assert comic_seen(db_path, "https://example.com/1") is False
