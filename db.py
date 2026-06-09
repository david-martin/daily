import sqlite3
from dataclasses import dataclass
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
        # Migration: add reason column to existing databases
        try:
            conn.execute("ALTER TABLE items ADD COLUMN reason TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.close()


def comic_seen(db_path: str, url: str) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM items WHERE url = ? AND is_comic = 1", (url,)
        ).fetchone()
    conn.close()
    return row is not None


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


def prev_briefing_date(db_path: str, date_str: str) -> Optional[str]:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT date FROM briefings WHERE date < ? ORDER BY date DESC LIMIT 1",
            (date_str,),
        ).fetchone()
    conn.close()
    return row[0] if row else None
