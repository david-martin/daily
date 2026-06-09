import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from db import Item

logger = logging.getLogger(__name__)


@lru_cache(maxsize=None)
def _env(templates_dir: str) -> Environment:
    return Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(["html", "html.j2"]),
    )


def generate_day(
    output_dir: str,
    templates_dir: str,
    date_str: str,
    items: list[Item],
    prev_date: Optional[str],
    scoring_info: Optional[dict] = None,
) -> None:
    ranked = [i for i in items if not i.is_comic]
    comics = [i for i in items if i.is_comic]
    if prev_date is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", prev_date):
        raise ValueError(f"prev_date must be YYYY-MM-DD, got: {prev_date!r}")
    html = _env(templates_dir).get_template("day.html.j2").render(
        date_str=date_str, ranked=ranked, comics=comics,
        prev_date=prev_date, scoring_info=scoring_info,
    )
    out = Path(output_dir) / f"{date_str}.html"
    out.write_text(html, encoding="utf-8")
    logger.info("Wrote %s", out)


def generate_index(
    output_dir: str,
    templates_dir: str,
    dates: list[str],
) -> None:
    html = _env(templates_dir).get_template("index.html.j2").render(dates=dates)
    out = Path(output_dir) / "index.html"
    out.write_text(html, encoding="utf-8")
    logger.info("Wrote %s", out)
