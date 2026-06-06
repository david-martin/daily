import pytest
import yaml
from pathlib import Path
from config import load, Config, Source, Scoring


def write_config(tmp_path, data):
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(data))
    return str(p)


def test_load_returns_config(tmp_path):
    p = write_config(tmp_path, {
        "sources": [{"name": "Test", "url": "https://example.com/rss"}],
        "scoring": {"profile": "I live in test city.", "categories": ["Local", "Tech"]},
        "output_dir": "/tmp/out",
    })
    c = load(p)
    assert isinstance(c, Config)


def test_load_source_defaults(tmp_path):
    p = write_config(tmp_path, {
        "sources": [{"name": "Test", "url": "https://example.com/rss"}],
        "scoring": {"profile": "x", "categories": ["A"]},
        "output_dir": "/tmp/out",
    })
    c = load(p)
    assert c.sources[0].comic is False


def test_load_comic_source(tmp_path):
    p = write_config(tmp_path, {
        "sources": [{"name": "XKCD", "url": "https://xkcd.com/atom.xml", "comic": True}],
        "scoring": {"profile": "x", "categories": ["A"]},
        "output_dir": "/tmp/out",
    })
    c = load(p)
    assert c.sources[0].comic is True


def test_load_scoring_defaults(tmp_path):
    p = write_config(tmp_path, {
        "sources": [{"name": "T", "url": "https://example.com/rss"}],
        "scoring": {"profile": "x", "categories": ["A"]},
        "output_dir": "/tmp/out",
    })
    c = load(p)
    assert c.scoring.top_n == 10
    assert c.scoring.min_score == 4.0
    assert c.model == "claude-haiku-4-5-20251001"


def test_load_custom_scoring(tmp_path):
    p = write_config(tmp_path, {
        "sources": [{"name": "T", "url": "https://example.com/rss"}],
        "scoring": {"profile": "x", "categories": ["A"], "top_n": 5, "min_score": 6.0},
        "output_dir": "/tmp/out",
        "model": "claude-sonnet-4-6",
    })
    c = load(p)
    assert c.scoring.top_n == 5
    assert c.scoring.min_score == 6.0
    assert c.model == "claude-sonnet-4-6"
