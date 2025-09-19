from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def connect(path: str | Path) -> sqlite3.Connection:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("""
    CREATE TABLE IF NOT EXISTS queue (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      topic TEXT NOT NULL,
      payload TEXT NOT NULL,
      tag TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'queued',   -- queued|processing|done|dead
      enqueued_ts TEXT NOT NULL,
      dequeued_ts TEXT,
      attempts INTEGER NOT NULL DEFAULT 0
    );
    """)
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_topic_tag ON queue(topic, tag);")
    con.execute("CREATE INDEX IF NOT EXISTS ix_queue_status ON queue(status);")
    return con


def enqueue(con: sqlite3.Connection, topic: str, tag: str, payload: dict) -> None:
    con.execute(
        "INSERT OR IGNORE INTO queue(topic, payload, tag, status, enqueued_ts) VALUES (?,?,?,?,?)",
        (topic, json.dumps(payload), tag, "queued", _utcnow_iso()),
    )
    con.commit()


def reserve(con: sqlite3.Connection, topic: str, visibility_timeout_sec: int = 10, max_attempts: int = 10) -> dict | None:
    cutoff = (datetime.now(UTC) - timedelta(seconds=visibility_timeout_sec)).isoformat()
    cur = con.execute(
        """
        SELECT id, payload, tag, status, attempts
        FROM queue
        WHERE topic = ?
          AND (
                status = 'queued'
             OR (status = 'processing' AND (dequeued_ts IS NULL OR dequeued_ts <= ?))
          )
        ORDER BY id ASC
        LIMIT 1
        """,
        (topic, cutoff),
    )
    row = cur.fetchone()
    if not row:
        return None
    id_, payload, tag, status, attempts = row
    if attempts >= max_attempts:
        con.execute("UPDATE queue SET status='dead' WHERE id=?", (id_,))
        con.commit()
        return None
    now = _utcnow_iso()
    con.execute(
        "UPDATE queue SET status='processing', attempts=attempts+1, dequeued_ts=? WHERE id=?",
        (now, id_),
    )
    con.commit()
    return {"id": id_, "payload": json.loads(payload), "tag": tag}


def ack(con: sqlite3.Connection, id_: int) -> None:
    con.execute("UPDATE queue SET status='done' WHERE id=?", (id_,))
    con.commit()


def nack(con: sqlite3.Connection, id_: int, dead: bool = False) -> None:
    con.execute(
        "UPDATE queue SET status=? WHERE id=?",
        (
            "dead" if dead else "queued",
            id_,
        ),
    )
    con.commit()


def depth(con: sqlite3.Connection, topic: str) -> int:
    return int(
        con.execute(
            "SELECT COUNT(*) FROM queue WHERE topic=? AND status IN ('queued','processing')",
            (topic,),
        ).fetchone()[0]
    )


def dead_letter_count(con: sqlite3.Connection, topic: str) -> int:
    """Get count of dead messages in topic."""
    result = con.execute(
        "SELECT COUNT(*) FROM queue WHERE topic=? AND status='dead'", (topic,)
    ).fetchone()
    return int(result[0]) if result else 0
