import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

import anthropic

from config import Config
from fetch import FetchedItem

logger = logging.getLogger(__name__)


@dataclass
class ScoredItem:
    title: str
    url: str
    source: str
    content: Optional[str]
    score: float
    rank: int
    is_comic: bool = False


def _build_prompt(items: list[FetchedItem], config: Config) -> str:
    categories = "\n".join(
        f"  {i + 1}. {c}" for i, c in enumerate(config.scoring.categories)
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

Category priority (higher number = higher priority):
{categories}

Return ONLY a JSON array with no other text:
[{{"id": 0, "score": 7}}, {{"id": 1, "score": 3}}, ...]

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
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    scores = json.loads(message.content[0].text.strip())
    score_map = {entry["id"]: float(entry["score"]) for entry in scores}

    candidates = [
        (i, score_map.get(i, 0.0))
        for i in range(len(items))
        if score_map.get(i, 0.0) >= config.scoring.min_score
    ]
    candidates.sort(key=lambda x: x[1], reverse=True)
    top = candidates[: config.scoring.top_n]

    return [
        ScoredItem(
            title=items[i].title,
            url=items[i].url,
            source=items[i].source,
            content=items[i].content,
            score=score,
            rank=rank + 1,
            is_comic=False,
        )
        for rank, (i, score) in enumerate(top)
    ]
