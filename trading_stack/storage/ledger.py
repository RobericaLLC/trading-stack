from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pandas as pd

Kind = Literal["INTENT", "ACK", "REJ", "PARTIAL", "FILL", "CANCEL", "PNL_SNAPSHOT"]


def _ensure_dt_utc(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def append_ledger(path: str | Path, rows: list[dict]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    if df.empty:
        return
    # enforce UTC ISO for ts and event_ts
    for col in ("ts", "event_ts"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True)
    if p.exists():
        old = pd.read_parquet(p)
        df = pd.concat([old, df], ignore_index=True)
    df.to_parquet(p, index=False)


def read_ledger(path: str | Path) -> pd.DataFrame:
    return pd.read_parquet(path)
