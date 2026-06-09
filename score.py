import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

import anthropic

from config import Config
from fetch import FetchedItem

logger = logging.getLogger(__name__)


class ScoreError(Exception):
    pass


@dataclass
class ScoredItem:
    title: str
    url: str
    source: str
    content: Optional[str]
    score: float
    rank: int
    reason: Optional[str] = None
    is_comic: bool = False


def _build_prompt(items: list[FetchedItem], config: Config) -> str:
    categories = "\n".join(
        f"  - {c}" for c in config.scoring.categories
    )
    item_lines = []
    for i, item in enumerate(items):
        snippet = re.sub(r"<[^>]+>", "", item.content or "")[:500].strip()
        item_lines.append(
            f"[{i}] source={item.source}\ntitle={item.title}\nsnippet={snippet}"
        )
    items_text = "\n\n".join(item_lines)

    return f"""Score each news item 1-10 for relevance to this personal profile:

{config.scoring.profile}

Category priority (listed highest to lowest priority):
{categories}

Return ONLY a JSON array with no other text. Each entry must include:
- "id": the item index
- "score": integer 1-10
- "reason": 6-10 words explaining the specific match — name the category and the concrete hook, not generic phrases like "relevant to interests"

Example: [{{"id": 0, "score": 8, "reason": "AI: practical LLM reasoning benchmark results"}}, ...]

Items to score:

{items_text}"""


def score_items(
    items: list[FetchedItem],
    config: Config,
    api_key: str,
) -> list[ScoredItem]:
    if not items:
        return []

    client = anthropic.Anthropic(api_key=api_key)
    prompt = _build_prompt(items, config)

    message = client.messages.create(
        model=config.model,
        max_tokens=max(2048, len(items) * 60),
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        raw = message.content[0].text.strip()
        # Strip markdown code fences if the model wrapped the JSON
        if raw.startswith("```"):
            raw = re.sub(r"^```[^\n]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        logger.debug("score API raw response: %s", raw[:200])
        scores = json.loads(raw)
        score_map = {entry["id"]: float(entry["score"]) for entry in scores}
        reason_map = {entry["id"]: entry.get("reason") for entry in scores}
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        raise ScoreError(f"invalid score response from API: {e}") from e

    if len(score_map) < len(items):
        logger.warning(
            "Model returned scores for %d of %d items; %d will be scored 0",
            len(score_map), len(items), len(items) - len(score_map),
        )

    candidates = [
        (i, score_map.get(i, 0.0))
        for i in range(len(items))
        if score_map.get(i, 0.0) >= config.scoring.min_score
    ]
    candidates.sort(key=lambda x: x[1], reverse=True)

    source_counts: dict[str, int] = {}
    top: list[tuple[int, float]] = []
    for i, score in candidates:
        src = items[i].source
        if source_counts.get(src, 0) >= config.scoring.max_per_source:
            continue
        source_counts[src] = source_counts.get(src, 0) + 1
        top.append((i, score))
        if len(top) >= config.scoring.top_n:
            break

    return [
        ScoredItem(
            title=items[i].title,
            url=items[i].url,
            source=items[i].source,
            content=items[i].content,
            score=score,
            rank=rank + 1,
            reason=reason_map.get(i),
            is_comic=False,
        )
        for rank, (i, score) in enumerate(top)
    ]
