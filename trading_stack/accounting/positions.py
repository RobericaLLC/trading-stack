from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class PositionSnapshot:
    symbol: str
    qty: float
    avg_cost: float
    realized_pnl: float

def _iter_fills_incremental(df: pd.DataFrame) -> Generator[dict[str, Any], None, None]:
    """
    Ledger FILL rows contain 'fill_qty' (incremental) and 'avg_px' (cumulative avg).
    Recover each incremental fill price using: p_i = (A_n*Q_n - A_{n-1}*Q_{n-1}) / (Q_n - Q_{n-1})
    Grouped by 'tag' to avoid cross-trade contamination.
    """
    need = {"kind","tag","symbol","side","fill_qty","avg_px","event_ts"}
    if not need.issubset(set(df.columns)):
        return
    df = df[df["kind"] == "FILL"].copy()
    df = df.sort_values(["tag", "event_ts"])
    prev: dict[str, tuple[float, float]] = {}  # tag -> (Q_prev, A_prev)
    for _, r in df.iterrows():
        tag = str(r["tag"])
        q = float(r.get("fill_qty", 0.0) or 0.0)
        a = float(r.get("avg_px", 0.0) or 0.0)       # cumulative average price after this fill
        if q <= 0 or a <= 0:
            continue
        q_prev, a_prev = prev.get(tag, (0.0, 0.0))
        q_new = q_prev + q
        px_i = a if q_prev == 0 else ((a * q_new) - (a_prev * q_prev)) / q
        prev[tag] = (q_new, a)
        yield dict(
            ts=r.get("event_ts"), tag=tag, symbol=str(r["symbol"]),
            side=str(r["side"]), qty=q, px=float(px_i)
        )

def compute_positions(ledger_path: str | Path) -> dict[str, PositionSnapshot]:
    p = Path(ledger_path)
    if not p.exists():
        return {}
    df = pd.read_parquet(p)
    snaps: dict[str, PositionSnapshot] = {}
    for f in _iter_fills_incremental(df):
        sym = f["symbol"]
        side = f["side"]
        q = float(f["qty"])
        px = float(f["px"])
        pos = snaps.get(sym, PositionSnapshot(symbol=sym, qty=0.0, avg_cost=0.0, realized_pnl=0.0))
        if side == "BUY":
            new_qty = pos.qty + q
            pos.avg_cost = (pos.avg_cost * pos.qty + px * q) / max(new_qty, 1e-9)
            pos.qty = new_qty
        else:  # SELL
            sell_qty = min(q, pos.qty)
            pos.realized_pnl += (px - pos.avg_cost) * sell_qty
            pos.qty -= sell_qty
            if pos.qty == 0:
                pos.avg_cost = 0.0
        snaps[sym] = pos
    return snaps

def write_snapshot(ledger_path: str | Path, out_path: str | Path) -> None:
    snaps = compute_positions(ledger_path)
    rows = [
        dict(symbol=s.symbol, qty=s.qty, avg_cost=s.avg_cost, realized_pnl=s.realized_pnl)
        for s in snaps.values()
    ]
    if not rows:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            columns=["symbol", "qty", "avg_cost", "realized_pnl"]
        ).to_parquet(out_path, index=False)
        return
    pd.DataFrame(rows).to_parquet(out_path, index=False)
