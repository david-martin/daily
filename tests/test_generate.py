import pytest
from pathlib import Path
from db import Item
import generate

TEMPLATES = str(Path(__file__).parent.parent / "templates")


@pytest.fixture
def items():
    return [
        Item(title="Top Story", url="https://example.com/1", source="Feed",
             content="<p>Article content here</p>", score=9.0, is_comic=False, rank=1),
        Item(title="Second Story", url="https://example.com/2", source="Feed",
             content="<p>More content</p>", score=7.0, is_comic=False, rank=2),
        Item(title="XKCD Today", url="https://xkcd.com/999/", source="XKCD",
             content='<a href="https://imgs.xkcd.com/test.png">[image →]</a>',
             score=None, is_comic=True, rank=None),
    ]


def test_generate_day_creates_file(tmp_path, items):
    generate.generate_day(str(tmp_path), TEMPLATES, "2026-06-06", items, prev_date=None)
    assert (tmp_path / "2026-06-06.html").exists()


def test_generate_day_contains_item_title(tmp_path, items):
    generate.generate_day(str(tmp_path), TEMPLATES, "2026-06-06", items, prev_date=None)
    html = (tmp_path / "2026-06-06.html").read_text()
    assert "Top Story" in html
    assert "Article content here" in html


def test_generate_day_contains_original_link(tmp_path, items):
    generate.generate_day(str(tmp_path), TEMPLATES, "2026-06-06", items, prev_date=None)
    html = (tmp_path / "2026-06-06.html").read_text()
    assert "https://example.com/1" in html


def test_generate_day_includes_comic(tmp_path, items):
    generate.generate_day(str(tmp_path), TEMPLATES, "2026-06-06", items, prev_date=None)
    html = (tmp_path / "2026-06-06.html").read_text()
    assert "XKCD Today" in html
    assert "[image →]" in html


def test_generate_day_includes_prev_link(tmp_path, items):
    generate.generate_day(str(tmp_path), TEMPLATES, "2026-06-06", items, prev_date="2026-06-05")
    html = (tmp_path / "2026-06-06.html").read_text()
    assert "2026-06-05.html" in html


def test_generate_day_no_prev_link_when_none(tmp_path, items):
    generate.generate_day(str(tmp_path), TEMPLATES, "2026-06-06", items, prev_date=None)
    html = (tmp_path / "2026-06-06.html").read_text()
    assert "2026-06-05.html" not in html


def test_generate_index_creates_file(tmp_path):
    generate.generate_index(str(tmp_path), TEMPLATES, ["2026-06-06", "2026-06-05"])
    assert (tmp_path / "index.html").exists()


def test_generate_index_lists_dates(tmp_path):
    generate.generate_index(str(tmp_path), TEMPLATES, ["2026-06-06", "2026-06-05"])
    html = (tmp_path / "index.html").read_text()
    assert "2026-06-06" in html
    assert "2026-06-05" in html
    assert "2026-06-06.html" in html


def test_xss_in_title_is_escaped(tmp_path):
    xss_items = [Item(title='<script>alert(1)</script>', url='https://example.com',
                      source='Feed', content=None, score=9.0, is_comic=False, rank=1)]
    generate.generate_day(str(tmp_path), TEMPLATES, "2026-06-06", xss_items, prev_date=None)
    html = (tmp_path / "2026-06-06.html").read_text()
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
