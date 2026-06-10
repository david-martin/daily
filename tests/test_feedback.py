import pytest
import yaml

import db
from db import Feedback
from feedback import (select_examples, render_snippet, render_raw, parse_raw,
                      EXAMPLE_CAP)


def fb(url, verdict, ai_score=8.0, title=None, source="Feed",
       rated_at="2026-06-10T12:00:00+00:00"):
    return Feedback(url=url, title=title or url, source=source,
                    ai_score=ai_score, verdict=verdict, rated_at=rated_at)


def test_select_examples_filters_verdict():
    feedback = [fb("a", "good"), fb("b", "bad"), fb("c", "skip")]
    assert select_examples(feedback, "good") == ["a (Feed)"]
    assert select_examples(feedback, "bad") == ["b (Feed)"]


def test_select_examples_prefers_disagreements():
    feedback = [
        # agreement: AI 8, reader agrees it's good — rated most recently
        fb("agree", "good", ai_score=8.0, rated_at="2026-06-10T12:00:00+00:00"),
        # disagreement: AI 4, reader says good — rated earlier
        fb("disagree", "good", ai_score=4.0, rated_at="2026-06-01T12:00:00+00:00"),
    ]
    result = select_examples(feedback, "good")
    assert result[0] == "disagree (Feed)"


def test_select_examples_bad_disagreement_is_high_score():
    feedback = [
        fb("agree", "bad", ai_score=3.0, rated_at="2026-06-10T12:00:00+00:00"),
        fb("disagree", "bad", ai_score=9.0, rated_at="2026-06-01T12:00:00+00:00"),
    ]
    result = select_examples(feedback, "bad")
    assert result[0] == "disagree (Feed)"


def test_select_examples_recent_first_within_group():
    feedback = [
        fb("older", "good", rated_at="2026-06-01T12:00:00+00:00"),
        fb("newer", "good", rated_at="2026-06-10T12:00:00+00:00"),
    ]
    result = select_examples(feedback, "good")
    assert result == ["newer (Feed)", "older (Feed)"]


def test_select_examples_caps():
    feedback = [fb(f"u{i}", "good") for i in range(EXAMPLE_CAP + 10)]
    assert len(select_examples(feedback, "good")) == EXAMPLE_CAP


def test_select_examples_none_score_is_not_disagreement():
    feedback = [fb("noscore", "good", ai_score=None)]
    assert select_examples(feedback, "good") == ["noscore (Feed)"]


def test_render_snippet_structure():
    feedback = [fb("good-one", "good"), fb("bad-one", "bad", ai_score=2.0)]
    data = yaml.safe_load(render_snippet(feedback))
    assert data["scoring"]["calibration"]["good"] == ["good-one (Feed)"]
    assert data["scoring"]["calibration"]["bad"] == ["bad-one (Feed)"]


def test_render_raw_round_trip():
    feedback = [
        fb("https://example.com/a", "good", ai_score=8.0),
        fb("https://example.com/b", "skip", ai_score=None),
    ]
    assert parse_raw(render_raw(feedback)) == feedback


def test_parse_raw_rejects_other_yaml():
    with pytest.raises(ValueError):
        parse_raw("scoring:\n  min_score: 7\n")


def test_import_into_fresh_db(tmp_path):
    src = str(tmp_path / "src.db")
    dst = str(tmp_path / "dst.db")
    db.init(src)
    db.init(dst)
    db.store_feedback(src, "https://example.com/a", "Title A", "Feed", 8.0,
                      "good", rated_at="2026-06-10T12:00:00+00:00")
    raw = render_raw(db.get_feedback(src))
    for f in parse_raw(raw):
        db.store_feedback(dst, f.url, f.title, f.source, f.ai_score,
                          f.verdict, rated_at=f.rated_at)
    assert db.get_feedback(dst) == db.get_feedback(src)
