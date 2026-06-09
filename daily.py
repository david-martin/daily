#!/usr/bin/env python3
import argparse
import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import config as cfg
import db
import fetch as fetcher
import score as scorer
import generate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

TEMPLATES_DIR = str(Path(__file__).parent / "templates")
DB_DEFAULT = str(Path(__file__).parent / "daily.db")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate daily briefing")
    parser.add_argument(
        "--config",
        default=os.environ.get("DAILY_CONFIG", "config.yaml"),
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("DAILY_DB", DB_DEFAULT),
    )
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY is not set")
        sys.exit(1)

    config = cfg.load(args.config)
    db.init(args.db)

    today = date.today().isoformat()
    logger.info("Generating briefing for %s", today)

    all_items: list[fetcher.FetchedItem] = []
    for source in config.sources:
        logger.info("Fetching %s", source.name)
        items = fetcher.fetch_source(source.name, source.url, source.comic)
        logger.info("  → %d items", len(items))
        all_items.extend(items)

    comics = [i for i in all_items if i.is_comic]
    regular = [i for i in all_items if not i.is_comic]

    new_comics = [c for c in comics if not db.comic_seen(args.db, c.url, before_date=today)]
    logger.info("%d new comic(s)", len(new_comics))

    logger.info("Scoring %d regular items", len(regular))
    scored = scorer.score_items(regular, config, api_key)
    logger.info("%d items kept after scoring", len(scored))

    db_items = [
        db.Item(
            title=s.title, url=s.url, source=s.source, content=s.content,
            score=s.score, is_comic=False, rank=s.rank, reason=s.reason,
        )
        for s in scored
    ] + [
        db.Item(
            title=c.title, url=c.url, source=c.source, content=c.content,
            score=None, is_comic=True, rank=None,
        )
        for c in new_comics
    ]

    generated_at = datetime.now(timezone.utc).isoformat()
    db.store_briefing(args.db, today, generated_at, db_items)

    Path(config.output_dir).mkdir(parents=True, exist_ok=True)
    prev_date = db.prev_briefing_date(args.db, today)
    stored = db.get_items_for_date(args.db, today)

    scoring_info = {
        "model": config.model,
        "categories": config.scoring.categories,
        "top_n": config.scoring.top_n,
        "max_per_source": config.scoring.max_per_source,
        "sources": [s.name for s in config.sources if not s.comic],
    }
    generate.generate_day(config.output_dir, TEMPLATES_DIR, today, stored, prev_date,
                          scoring_info=scoring_info)
    all_dates = db.get_briefing_dates(args.db)
    generate.generate_index(config.output_dir, TEMPLATES_DIR, all_dates)

    logger.info("Done — briefing for %s at %s", today, config.output_dir)


if __name__ == "__main__":
    main()
