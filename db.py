import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Item:
    title: str
    url: str
    source: str
    content: Optional[str]
    score: Optional[float]
    is_comic: bool
    rank: Optional[int]
    reason: Optional[str] = None


@dataclass
class Feedback:
    url: str
    title: str
    source: str
    ai_score: Optional[float]
    verdict: str  # "good", "bad", or "skip"
    rated_at: str


def init(db_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS briefings (
                date         TEXT PRIMARY KEY,
                generated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                date     TEXT    NOT NULL,
                title    TEXT    NOT NULL,
                url      TEXT    NOT NULL,
                source   TEXT    NOT NULL,
                content  TEXT,
                score    REAL,
                is_comic INTEGER DEFAULT 0,
                rank     INTEGER,
                reason   TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                url      TEXT PRIMARY KEY,
                title    TEXT NOT NULL,
                source   TEXT NOT NULL,
                ai_score REAL,
                verdict  TEXT NOT NULL CHECK (verdict IN ('good', 'bad', 'skip')),
                rated_at TEXT NOT NULL
            )
        """)
        # Migration: add reason column to existing databases
        try:
            conn.execute("ALTER TABLE items ADD COLUMN reason TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.close()


def comic_seen(db_path: str, url: str, before_date: Optional[str] = None) -> bool:
    with sqlite3.connect(db_path) as conn:
        if before_date:
            row = conn.execute(
                "SELECT 1 FROM items WHERE url = ? AND is_comic = 1 AND date < ?",
                (url, before_date),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT 1 FROM items WHERE url = ? AND is_comic = 1", (url,)
            ).fetchone()
    conn.close()
    return row is not None


def seen_urls(db_path: str, before_date: Optional[str] = None) -> set[str]:
    """URLs of items stored before `before_date` (all dates if None).

    Used to drop items already shown on a previous day, so the same
    feed entry isn't re-shown while it lingers in an RSS feed. Using
    `before_date=today` lets same-day re-runs keep their own items.
    """
    with sqlite3.connect(db_path) as conn:
        if before_date:
            rows = conn.execute(
                "SELECT DISTINCT url FROM items WHERE date < ?", (before_date,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT DISTINCT url FROM items").fetchall()
    conn.close()
    return {r[0] for r in rows}


def store_briefing(
    db_path: str,
    date_str: str,
    generated_at: str,
    items: list[Item],
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO briefings (date, generated_at) VALUES (?, ?)",
            (date_str, generated_at),
        )
        conn.execute("DELETE FROM items WHERE date = ?", (date_str,))
        for item in items:
            conn.execute(
                """INSERT INTO items
                   (date, title, url, source, content, score, is_comic, rank, reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (date_str, item.title, item.url, item.source, item.content,
                 item.score, int(item.is_comic), item.rank, item.reason),
            )
    conn.close()


def get_items_for_date(db_path: str, date_str: str) -> list[Item]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """SELECT title, url, source, content, score, is_comic, rank, reason
               FROM items WHERE date = ?
               ORDER BY is_comic ASC, rank ASC NULLS LAST""",
            (date_str,),
        ).fetchall()
    conn.close()
    return [
        Item(title=r[0], url=r[1], source=r[2], content=r[3],
             score=r[4], is_comic=bool(r[5]), rank=r[6], reason=r[7])
        for r in rows
    ]


def get_briefing_dates(db_path: str) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT date FROM briefings ORDER BY date DESC"
        ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_unrated_items(db_path: str, days: int = 5) -> list[Item]:
    """Non-comic items from the last `days` briefings with no feedback yet.

    Deduplicated by URL (an item can appear in several briefings); most
    recent first, then highest-scored first.
    """
    with sqlite3.connect(db_path) as conn:
        dates = [r[0] for r in conn.execute(
            "SELECT date FROM briefings ORDER BY date DESC LIMIT ?", (days,)
        ).fetchall()]
        rows = []
        if dates:
            placeholders = ",".join("?" * len(dates))
            rows = conn.execute(
                f"""SELECT title, url, source, MAX(score), reason, MAX(date)
                    FROM items
                    WHERE is_comic = 0 AND date IN ({placeholders})
                      AND url NOT IN (SELECT url FROM feedback)
                    GROUP BY url
                    ORDER BY MAX(date) DESC, MAX(score) DESC""",
                dates,
            ).fetchall()
    conn.close()
    return [
        Item(title=r[0], url=r[1], source=r[2], content=None,
             score=r[3], is_comic=False, rank=None, reason=r[4])
        for r in rows
    ]


def store_feedback(
    db_path: str,
    url: str,
    title: str,
    source: str,
    ai_score: Optional[float],
    verdict: str,
    rated_at: Optional[str] = None,
) -> None:
    if rated_at is None:
        rated_at = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO feedback
               (url, title, source, ai_score, verdict, rated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (url, title, source, ai_score, verdict, rated_at),
        )
    conn.close()


def get_feedback(db_path: str) -> list[Feedback]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """SELECT url, title, source, ai_score, verdict, rated_at
               FROM feedback ORDER BY rated_at DESC"""
        ).fetchall()
    conn.close()
    return [
        Feedback(url=r[0], title=r[1], source=r[2], ai_score=r[3],
                 verdict=r[4], rated_at=r[5])
        for r in rows
    ]


def prev_briefing_date(db_path: str, date_str: str) -> Optional[str]:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT date FROM briefings WHERE date < ? ORDER BY date DESC LIMIT 1",
            (date_str,),
        ).fetchone()
    conn.close()
    return row[0] if row else None
