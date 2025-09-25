from __future__ import annotations
from pathlib import Path
from typing import Literal
from datetime import datetime, timezone
import pandas as pd
from .atomic import FileLock, atomic_write_parquet

Kind = Literal["INTENT","ACK","REJ","PARTIAL","FILL","CANCEL","PNL_SNAPSHOT","INTENT_SHADOW"]

# minimal, unified dtype hints (flexible—NaN allowed)
_NUMERIC = ["qty","fill_qty","avg_px","limit","shortfall_bps"]
_TIME = ["ts","event_ts"]

def _coerce(df: pd.DataFrame) -> pd.DataFrame:
    for c in _TIME:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], utc=True, errors="coerce")
    for c in _NUMERIC:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "kind" in df.columns:
        df["kind"] = df["kind"].astype("string")
    if "tag" in df.columns:
        df["tag"] = df["tag"].astype("string")
    if "symbol" in df.columns:
        df["symbol"] = df["symbol"].astype("string")
    if "side" in df.columns:
        df["side"] = df["side"].astype("string")
    return df

def append_ledger(path: str | Path, rows: list[dict]) -> None:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    df_new = pd.DataFrame(rows)
    if df_new.empty: return
    df_new = _coerce(df_new)

    with FileLock(p, timeout=5.0):
        if p.exists():
            try:
                old = pd.read_parquet(p)
            except Exception:
                # fall back to new-only if file is unreadable; preserve progress
                old = pd.DataFrame()
            # union columns safely
            for col in set(old.columns) - set(df_new.columns):
                df_new[col] = pd.NA
            for col in set(df_new.columns) - set(old.columns):
                old[col] = pd.NA
            df = pd.concat([old, df_new], ignore_index=True)
        else:
            df = df_new
        df = _coerce(df)
        atomic_write_parquet(p, df)

def read_ledger(path: str | Path) -> pd.DataFrame:
    return pd.read_parquet(path)