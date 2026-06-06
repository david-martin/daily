import json
import pytest
from unittest.mock import patch, MagicMock
from score import score_items, _build_prompt, ScoredItem, ScoreError
from fetch import FetchedItem
from config import Config, Source, Scoring


@pytest.fixture
def cfg():
    return Config(
        sources=[],
        scoring=Scoring(
            profile="I live in Test City.",
            categories=["Local news", "Tech"],
            top_n=3,
            min_score=4.0,
        ),
        output_dir="/tmp/out",
        model="claude-haiku-4-5-20251001",
    )


@pytest.fixture
def items():
    return [
        FetchedItem(title=f"Article {i}", url=f"https://example.com/{i}",
                    source="Feed", content=f"<p>Content {i}</p>", is_comic=False)
        for i in range(5)
    ]


def _mock_response(scores: list[dict]) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(scores))]
    return msg


def test_build_prompt_contains_profile(cfg, items):
    prompt = _build_prompt(items, cfg)
    assert "Test City" in prompt


def test_build_prompt_contains_categories(cfg, items):
    prompt = _build_prompt(items, cfg)
    assert "Local news" in prompt
    assert "Tech" in prompt


def test_build_prompt_contains_all_titles(cfg, items):
    prompt = _build_prompt(items, cfg)
    for i in range(5):
        assert f"Article {i}" in prompt


def test_score_items_empty_input_returns_empty(cfg):
    result = score_items([], cfg, "key")
    assert result == []


def test_score_items_filters_below_min_score(cfg, items):
    scores = [
        {"id": 0, "score": 8}, {"id": 1, "score": 3},
        {"id": 2, "score": 7}, {"id": 3, "score": 2},
        {"id": 4, "score": 9},
    ]
    with patch("anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _mock_response(scores)
        result = score_items(items, cfg, "key")
    # top_n=3, only 3 items >= min_score=4.0
    assert len(result) == 3
    for r in result:
        assert r.score >= 4.0


def test_score_items_sorted_by_score_desc(cfg, items):
    scores = [
        {"id": 0, "score": 5}, {"id": 1, "score": 9},
        {"id": 2, "score": 6}, {"id": 3, "score": 4},
        {"id": 4, "score": 8},
    ]
    with patch("anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _mock_response(scores)
        result = score_items(items, cfg, "key")
    assert result[0].score >= result[1].score >= result[2].score


def test_score_items_assigns_sequential_rank(cfg, items):
    scores = [{"id": i, "score": 5 + i} for i in range(5)]
    with patch("anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _mock_response(scores)
        result = score_items(items, cfg, "key")
    assert [r.rank for r in result] == list(range(1, len(result) + 1))


def test_score_items_uses_configured_model(cfg, items):
    scores = [{"id": i, "score": 5} for i in range(5)]
    with patch("anthropic.Anthropic") as mock_cls:
        mock_instance = mock_cls.return_value
        mock_instance.messages.create.return_value = _mock_response(scores)
        score_items(items, cfg, "key")
        call_kwargs = mock_instance.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-haiku-4-5-20251001"


def test_score_items_raises_on_malformed_response(cfg, items):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="Sorry, I cannot score these items.")]
    with patch("anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = mock_msg
        with pytest.raises(ScoreError):
            score_items(items, cfg, "key")


def test_score_items_handles_markdown_fenced_response(cfg, items):
    scores = [{"id": i, "score": 5 + i} for i in range(5)]
    fenced = f"```json\n{json.dumps(scores)}\n```"
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=fenced)]
    with patch("anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = mock_msg
        result = score_items(items, cfg, "key")
    assert len(result) == 3


def test_score_items_handles_partial_response(cfg, items):
    # Model returns scores for only items 0, 2, 4 — items 1 and 3 get score 0 (below min)
    scores = [{"id": 0, "score": 8}, {"id": 2, "score": 7}, {"id": 4, "score": 9}]
    with patch("anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _mock_response(scores)
        result = score_items(items, cfg, "key")
    assert len(result) == 3
    assert all(r.score >= 4.0 for r in result)


def test_score_items_forwards_api_key(cfg, items):
    scores = [{"id": i, "score": 5} for i in range(5)]
    with patch("anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _mock_response(scores)
        score_items(items, cfg, "my-secret-key")
        assert mock_cls.call_args.kwargs["api_key"] == "my-secret-key"
