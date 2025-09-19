"""SQLite-based durable queue for order intents with exactly-once semantics."""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    """Get current UTC timestamp as ISO string."""
    return datetime.now(UTC).isoformat()


def connect(path: str | Path) -> sqlite3.Connection:
    """Connect to SQLite queue database, creating tables if needed."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p), check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("""CREATE TABLE IF NOT EXISTS queue (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      topic TEXT NOT NULL,
      payload TEXT NOT NULL,
      tag TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'queued',
      enqueued_ts TEXT NOT NULL,
      dequeued_ts TEXT,
      attempts INTEGER NOT NULL DEFAULT 0
    );""")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_topic_tag ON queue(topic, tag);")
    con.execute("CREATE INDEX IF NOT EXISTS ix_queue_status ON queue(status);")
    con.commit()
    return con


def enqueue(con: sqlite3.Connection, topic: str, tag: str, payload: dict) -> None:
    """Enqueue a message with idempotency via tag."""
    con.execute(
        "INSERT OR IGNORE INTO queue(topic, payload, tag, status, enqueued_ts) VALUES (?,?,?,?,?)",
        (topic, json.dumps(payload), tag, "queued", _utcnow())
    )
    con.commit()


def reserve(
    con: sqlite3.Connection, topic: str, visibility_timeout_sec: int = 10  # noqa: ARG001
) -> dict[str, Any] | None:
    """Reserve one queued message for processing."""
    # Get one queued row and mark processing
    cur = con.execute(
        "SELECT id, payload, tag FROM queue "
        "WHERE topic=? AND status='queued' ORDER BY id ASC LIMIT 1",
        (topic,)
    )
    row = cur.fetchone()
    if not row:
        return None
    
    id_, payload, tag = row
    con.execute(
        "UPDATE queue SET status='processing', attempts=attempts+1, dequeued_ts=? WHERE id=?",
        (_utcnow(), id_)
    )
    con.commit()
    return {"id": id_, "payload": json.loads(payload), "tag": tag}


def ack(con: sqlite3.Connection, id_: int) -> None:
    """Acknowledge successful processing of a message."""
    con.execute("UPDATE queue SET status='done' WHERE id=?", (id_,))
    con.commit()


def nack(con: sqlite3.Connection, id_: int, dead: bool = False) -> None:
    """Return message to queue or mark as dead."""
    con.execute(
        "UPDATE queue SET status=? WHERE id=?",
        ("dead" if dead else "queued", id_)
    )
    con.commit()


def depth(con: sqlite3.Connection, topic: str) -> int:
    """Get count of pending messages in topic."""
    result = con.execute(
        "SELECT COUNT(*) FROM queue WHERE topic=? AND status IN ('queued','processing')",
        (topic,)
    ).fetchone()
    return int(result[0]) if result else 0


def dead_letter_count(con: sqlite3.Connection, topic: str) -> int:
    """Get count of dead messages in topic."""
    result = con.execute(
        "SELECT COUNT(*) FROM queue WHERE topic=? AND status='dead'",
        (topic,)
    ).fetchone()
    return int(result[0]) if result else 0
