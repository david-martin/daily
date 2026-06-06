from dataclasses import dataclass
import yaml


@dataclass
class Source:
    name: str
    url: str
    comic: bool = False


@dataclass
class Scoring:
    profile: str
    categories: list[str]
    top_n: int = 10
    min_score: float = 4.0


@dataclass
class Config:
    sources: list[Source]
    scoring: Scoring
    output_dir: str
    model: str = "claude-haiku-4-5-20251001"


def load(path: str) -> Config:
    with open(path) as f:
        data = yaml.safe_load(f)

    sources = [
        Source(
            name=s["name"],
            url=s["url"],
            comic=s.get("comic", False),
        )
        for s in data["sources"]
    ]

    sd = data["scoring"]
    scoring = Scoring(
        profile=sd["profile"],
        categories=sd["categories"],
        top_n=sd.get("top_n", 10),
        min_score=float(sd.get("min_score", 4.0)),
    )

    return Config(
        sources=sources,
        scoring=scoring,
        output_dir=data["output_dir"],
        model=data.get("model", "claude-haiku-4-5-20251001"),
    )
