import pytest
import sqlite3
from db import (Item, init, comic_seen, store_briefing, get_items_for_date,
                get_briefing_dates, prev_briefing_date, get_unrated_items,
                store_feedback, get_feedback, seen_urls)


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


def test_seen_urls_empty_db(db_path):
    assert seen_urls(db_path) == set()


def test_seen_urls_returns_stored(db_path):
    items = [Item(title="A", url="https://example.com/a", source="Feed",
                  content=None, score=8.0, is_comic=False, rank=1)]
    store_briefing(db_path, "2026-06-06", "2026-06-06T07:00:00Z", items)
    assert seen_urls(db_path) == {"https://example.com/a"}


def test_seen_urls_before_date_excludes_same_day(db_path):
    items = [Item(title="A", url="https://example.com/a", source="Feed",
                  content=None, score=8.0, is_comic=False, rank=1)]
    store_briefing(db_path, "2026-06-06", "2026-06-06T07:00:00Z", items)
    # Same-day re-run: today's own items must not count as already seen.
    assert seen_urls(db_path, before_date="2026-06-06") == set()
    # A later day sees them as already shown.
    assert seen_urls(db_path, before_date="2026-06-07") == {"https://example.com/a"}


def test_seen_urls_includes_comics(db_path):
    items = [Item(title="C", url="https://xkcd.com/1/", source="XKCD",
                  content=None, score=None, is_comic=True, rank=None)]
    store_briefing(db_path, "2026-06-06", "2026-06-06T07:00:00Z", items)
    assert "https://xkcd.com/1/" in seen_urls(db_path)


def test_init_creates_feedback_table(db_path):
    with sqlite3.connect(db_path) as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    assert "feedback" in tables


def test_store_and_get_feedback(db_path):
    store_feedback(db_path, "https://example.com/1", "Title", "Feed", 8.0, "good")
    fb = get_feedback(db_path)
    assert len(fb) == 1
    assert fb[0].url == "https://example.com/1"
    assert fb[0].verdict == "good"
    assert fb[0].ai_score == 8.0
    assert fb[0].rated_at  # auto-populated


def test_store_feedback_upserts(db_path):
    store_feedback(db_path, "https://example.com/1", "T", "F", 8.0, "good")
    store_feedback(db_path, "https://example.com/1", "T", "F", 8.0, "bad")
    fb = get_feedback(db_path)
    assert len(fb) == 1
    assert fb[0].verdict == "bad"


def test_store_feedback_explicit_rated_at(db_path):
    store_feedback(db_path, "https://example.com/1", "T", "F", None, "skip",
                   rated_at="2026-06-01T00:00:00+00:00")
    fb = get_feedback(db_path)
    assert fb[0].rated_at == "2026-06-01T00:00:00+00:00"
    assert fb[0].ai_score is None


def test_get_unrated_items_excludes_rated_and_comics(db_path):
    items = [
        Item(title="Rated", url="https://example.com/a", source="Feed",
             content=None, score=8.0, is_comic=False, rank=1),
        Item(title="Unrated", url="https://example.com/b", source="Feed",
             content=None, score=7.0, is_comic=False, rank=2),
        Item(title="Comic", url="https://xkcd.com/1/", source="XKCD",
             content=None, score=None, is_comic=True, rank=None),
    ]
    store_briefing(db_path, "2026-06-06", "2026-06-06T07:00:00Z", items)
    store_feedback(db_path, "https://example.com/a", "Rated", "Feed", 8.0, "good")
    unrated = get_unrated_items(db_path)
    assert [i.title for i in unrated] == ["Unrated"]


def test_get_unrated_items_skip_counts_as_rated(db_path):
    items = [Item(title="Skipped", url="https://example.com/a", source="Feed",
                  content=None, score=8.0, is_comic=False, rank=1)]
    store_briefing(db_path, "2026-06-06", "2026-06-06T07:00:00Z", items)
    store_feedback(db_path, "https://example.com/a", "Skipped", "Feed", 8.0, "skip")
    assert get_unrated_items(db_path) == []


def test_get_unrated_items_respects_days(db_path):
    for d, title in [("2026-06-01", "Old"), ("2026-06-05", "Mid"),
                     ("2026-06-06", "New")]:
        store_briefing(db_path, d, f"{d}T07:00:00Z", [
            Item(title=title, url=f"https://example.com/{title}", source="Feed",
                 content=None, score=7.0, is_comic=False, rank=1)])
    titles = {i.title for i in get_unrated_items(db_path, days=2)}
    assert titles == {"Mid", "New"}


def test_get_unrated_items_dedupes_url(db_path):
    for d in ["2026-06-05", "2026-06-06"]:
        store_briefing(db_path, d, f"{d}T07:00:00Z", [
            Item(title="Same", url="https://example.com/same", source="Feed",
                 content=None, score=7.0, is_comic=False, rank=1)])
    assert len(get_unrated_items(db_path)) == 1


def test_get_unrated_items_includes_reason(db_path):
    items = [Item(title="T", url="https://example.com/1", source="Feed",
                  content=None, score=8.0, is_comic=False, rank=1,
                  reason="AI: concrete hook")]
    store_briefing(db_path, "2026-06-06", "2026-06-06T07:00:00Z", items)
    assert get_unrated_items(db_path)[0].reason == "AI: concrete hook"


def test_get_unrated_items_empty_db(db_path):
    assert get_unrated_items(db_path) == []
