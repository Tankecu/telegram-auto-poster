"""Post scheduling logic — pure and testable, no aiogram imports."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "posts.db"

MAX_ATTEMPTS = 3
RETRY_DELAY_MIN = 2  # minutes between attempts

QUICK_OPTIONS = [
    ("in_1h", "In 1 hour"),
    ("tonight_18", "Tonight at 18:00"),
    ("tomorrow_9", "Tomorrow at 09:00"),
]


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id TEXT NOT NULL,
            text TEXT NOT NULL,
            publish_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',  -- queued | published | failed
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_posts_due ON posts(status, publish_at);
        """
    )
    return conn


def resolve_time(choice: str, now: datetime | None = None) -> datetime:
    """Turn a quick option id or a custom HH:MM into an absolute datetime."""
    now = now or datetime.now()
    if choice == "in_1h":
        return now + timedelta(hours=1)
    if choice == "tonight_18":
        candidate = now.replace(hour=18, minute=0, second=0, microsecond=0)
        return candidate if candidate > now else candidate + timedelta(days=1)
    if choice == "tomorrow_9":
        candidate = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        return candidate
    m = __import__("re").fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", choice)
    if not m:
        raise ValueError(f"Unknown time choice: {choice!r}")
    candidate = now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
    return candidate if candidate > now else candidate + timedelta(days=1)


def queue_post(conn: sqlite3.Connection, *, owner_id: str, text: str, publish_at: datetime) -> int:
    cur = conn.execute(
        "INSERT INTO posts (owner_id, text, publish_at) VALUES (?, ?, ?)",
        (owner_id, text[:4000], publish_at.strftime("%Y-%m-%d %H:%M")),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def due_posts(conn: sqlite3.Connection, now: datetime | None = None) -> list[sqlite3.Row]:
    now = now or datetime.now()
    return conn.execute(
        "SELECT * FROM posts WHERE status = 'queued' AND publish_at <= ? ORDER BY publish_at LIMIT 10",
        (now.strftime("%Y-%m-%d %H:%M"),),
    ).fetchall()


def mark_published(conn: sqlite3.Connection, post_id: int) -> None:
    conn.execute("UPDATE posts SET status = 'published' WHERE id = ?", (post_id,))
    conn.commit()


def mark_failed_attempt(conn: sqlite3.Connection, post_id: int, error: str) -> None:
    """Increment attempts; after MAX_ATTEMPTS the post is dead, otherwise it stays queued."""
    row = conn.execute("SELECT attempts FROM posts WHERE id = ?", (post_id,)).fetchone()
    attempts = (row["attempts"] if row else 0) + 1
    status = "failed" if attempts >= MAX_ATTEMPTS else "queued"
    conn.execute(
        "UPDATE posts SET attempts = ?, status = ?, last_error = ? WHERE id = ?",
        (attempts, status, error[:300], post_id),
    )
    conn.commit()


def cancel_post(conn: sqlite3.Connection, post_id: int, owner_id: str) -> bool:
    cur = conn.execute(
        "DELETE FROM posts WHERE id = ? AND owner_id = ? AND status = 'queued'", (post_id, owner_id)
    )
    conn.commit()
    return cur.rowcount > 0


def queue_of(conn: sqlite3.Connection, owner_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM posts WHERE owner_id = ? AND status = 'queued' ORDER BY publish_at", (owner_id,)
    ).fetchall()


def minutes_until(post_publish_at: str, now: datetime | None = None) -> int:
    dt = datetime.strptime(post_publish_at, "%Y-%m-%d %H:%M")
    return max(0, round((dt - (now or datetime.now())).total_seconds() / 60))
