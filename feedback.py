#!/usr/bin/env python3
"""Rate past briefing items to build calibration examples for scoring.

Usage:
    feedback.py rate [--days 5]      interactive rating session
    feedback.py export [--raw] [-o FILE]
    feedback.py import FILE
"""
import argparse
import os
import sys
from dataclasses import asdict
from pathlib import Path

import yaml

import db

DB_DEFAULT = str(Path(__file__).parent / "daily.db")

EXAMPLE_CAP = 20


def _is_disagreement(fb: db.Feedback) -> bool:
    """True when the reader's verdict contradicts the AI score."""
    if fb.ai_score is None:
        return False
    if fb.verdict == "bad":
        return fb.ai_score >= 7
    if fb.verdict == "good":
        return fb.ai_score < 7
    return False


def select_examples(
    feedback: list[db.Feedback], verdict: str, cap: int = EXAMPLE_CAP
) -> list[str]:
    """Pick up to `cap` calibration examples for one verdict.

    Disagreements with the AI score come first (they teach the model the
    most), then most recently rated.
    """
    matching = [f for f in feedback if f.verdict == verdict]
    matching.sort(key=lambda f: f.rated_at, reverse=True)
    matching.sort(key=lambda f: 0 if _is_disagreement(f) else 1)
    return [f"{f.title} ({f.source})" for f in matching[:cap]]


def render_snippet(feedback: list[db.Feedback]) -> str:
    """YAML calibration block ready to merge into config.yaml."""
    data = {"scoring": {"calibration": {
        "good": select_examples(feedback, "good"),
        "bad": select_examples(feedback, "bad"),
    }}}
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True,
                          default_flow_style=False)


def render_raw(feedback: list[db.Feedback]) -> str:
    """Full portable verdict list, importable with `feedback.py import`."""
    data = {"feedback": [asdict(f) for f in feedback]}
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True,
                          default_flow_style=False)


def parse_raw(text: str) -> list[db.Feedback]:
    data = yaml.safe_load(text)
    if not isinstance(data, dict) or "feedback" not in data:
        raise ValueError("not a feedback file: missing top-level 'feedback' key")
    return [
        db.Feedback(
            url=e["url"], title=e["title"], source=e["source"],
            ai_score=e.get("ai_score"), verdict=e["verdict"],
            rated_at=e["rated_at"],
        )
        for e in data["feedback"]
    ]


def _read_key() -> str:
    """Read a single keypress; fall back to line input off a TTY."""
    if not sys.stdin.isatty():
        line = input().strip()
        return line[0] if line else " "
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def cmd_rate(args: argparse.Namespace) -> None:
    items = db.get_unrated_items(args.db, args.days)
    if not items:
        print("Nothing to rate — all items from the last "
              f"{args.days} briefings already have feedback.")
        return
    total = len(items)
    rated = 0
    for n, item in enumerate(items, 1):
        score_txt = f"{int(item.score)}/10" if item.score is not None else "–/10"
        print(f"\n[{n}/{total}] {score_txt} · {item.source}")
        print(f"  {item.title}")
        if item.reason:
            print(f"  AI: {item.reason}")
        print("\n  (y) good pick  (n) bad pick  (s) skip  (q) quit")
        while True:
            key = _read_key().lower()
            if key in ("y", "n", "s", "q"):
                break
        if key == "q":
            break
        verdict = {"y": "good", "n": "bad", "s": "skip"}[key]
        db.store_feedback(args.db, item.url, item.title, item.source,
                          item.score, verdict)
        rated += 1
    print(f"\nSaved {rated} verdict(s). "
          f"Run 'feedback.py export' for a config snippet.")


def cmd_export(args: argparse.Namespace) -> None:
    feedback = db.get_feedback(args.db)
    if not feedback:
        print("No feedback yet — run 'feedback.py rate' first.", file=sys.stderr)
        sys.exit(1)
    out = render_raw(feedback) if args.raw else render_snippet(feedback)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(out, end="")


def cmd_import(args: argparse.Namespace) -> None:
    text = Path(args.file).read_text(encoding="utf-8")
    entries = parse_raw(text)
    for f in entries:
        db.store_feedback(args.db, f.url, f.title, f.source, f.ai_score,
                          f.verdict, rated_at=f.rated_at)
    print(f"Imported {len(entries)} verdict(s) into {args.db}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default=os.environ.get("DAILY_DB", DB_DEFAULT),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_rate = sub.add_parser("rate", help="interactively rate unrated items")
    p_rate.add_argument("--days", type=int, default=5,
                        help="how many recent briefings to pull from")
    p_rate.set_defaults(func=cmd_rate)

    p_export = sub.add_parser("export", help="export calibration snippet or raw verdicts")
    p_export.add_argument("--raw", action="store_true",
                          help="full portable verdict list instead of config snippet")
    p_export.add_argument("-o", "--output", help="write to file instead of stdout")
    p_export.set_defaults(func=cmd_export)

    p_import = sub.add_parser("import", help="import a raw feedback file")
    p_import.add_argument("file")
    p_import.set_defaults(func=cmd_import)

    args = parser.parse_args()
    db.init(args.db)
    args.func(args)


if __name__ == "__main__":
    main()
