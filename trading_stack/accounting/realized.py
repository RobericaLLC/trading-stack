from __future__ import annotations

from pathlib import Path

import pandas as pd

PathLike = str | Path

def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "event_ts", "symbol", "realized_pnl_delta",
            "realized_pnl_cum", "position_qty", "avg_cost"
        ]
    )

def realized_pnl_timeseries(ledger_path: PathLike, symbol: str) -> pd.DataFrame:
    """Compute timestamped realized P&L from FILL rows using average-cost accounting."""
    p = Path(ledger_path)
    if not p.exists():
        return _empty_df()
    df = pd.read_parquet(p)
    if df.empty:
        return _empty_df()

    fills = df[df["kind"] == "FILL"].copy()
    if fills.empty:
        return _empty_df()

    # Ensure FILL rows have symbol/side; join with INTENT by tag if missing
    need_cols = {"symbol", "side"}
    if not need_cols.issubset(fills.columns) or fills[list(need_cols)].isna().any().any():
        intents = df[df["kind"] == "INTENT"][["tag", "symbol", "side"]].drop_duplicates()
        fills = fills.merge(intents, on="tag", how="left", suffixes=("", "_i"))
        for c in ("symbol", "side"):
            if c not in fills.columns or fills[c].isna().any():
                fills[c] = fills[f"{c}_i"]

    fills = fills[fills["symbol"] == symbol].copy()
    if fills.empty:
        return _empty_df()

    fills["event_ts"] = pd.to_datetime(fills["event_ts"], utc=True)
    fills = fills.sort_values(["event_ts", "tag"]).reset_index(drop=True)
    fills["fill_qty"] = fills["fill_qty"].astype(float)
    fills["avg_px"] = fills["avg_px"].astype(float)

    # Reconstruct per-fill prices from cumulative avg per tag
    def per_tag_px(g: pd.DataFrame) -> pd.DataFrame:
        qprev = 0.0
        aprev = 0.0
        px = []
        for _, r in g.iterrows():
            q = float(r["fill_qty"])
            a = float(r["avg_px"])           # cumulative avg after this fill
            qnew = qprev + q
            px_i = a if qprev == 0 else ((a * qnew) - (aprev * qprev)) / q
            px.append(px_i)
            qprev, aprev = qnew, a
        g = g.copy()
        g["fill_px"] = px
        return g

    fills = fills.groupby("tag", group_keys=False).apply(per_tag_px)

    # Run position + realized P&L (average cost)
    pos_qty = 0.0
    avg_cost = 0.0
    realized_cum = 0.0
    deltas, qtys, costs = [], [], []
    for _, r in fills.iterrows():
        side = str(r["side"]).upper()
        q = float(r["fill_qty"])
        px = float(r["fill_px"])
        delta = 0.0

        if side == "BUY":
            if pos_qty < 0:  # covering short
                matched = min(q, -pos_qty)
                delta += (avg_cost - px) * matched
                pos_qty += matched
                q -= matched
                if pos_qty == 0 and q > 0 or q > 0:
                    avg_cost = px
                    pos_qty += q
            else:
                new_qty = pos_qty + q
                avg_cost = (avg_cost * pos_qty + px * q) / (new_qty if new_qty != 0 else 1.0)
                pos_qty = new_qty

        else:  # SELL
            if pos_qty > 0:  # reducing long
                matched = min(q, pos_qty)
                delta += (px - avg_cost) * matched
                pos_qty -= matched
                q -= matched
                if pos_qty == 0 and q > 0 or q > 0:
                    avg_cost = px
                    pos_qty -= q
            else:  # increasing short
                size = abs(pos_qty)
                new_size = size + q
                if pos_qty < 0:
                    avg_cost = (avg_cost * size + px * q) / (new_size if new_size != 0 else 1.0)
                else:
                    avg_cost = px
                pos_qty -= q

        realized_cum += delta
        deltas.append(delta)
        qtys.append(pos_qty)
        costs.append(avg_cost)

    out = fills[["event_ts", "symbol"]].copy()
    out["realized_pnl_delta"] = deltas
    out["realized_pnl_cum"] = pd.Series(deltas).cumsum()
    out["position_qty"] = qtys
    out["avg_cost"] = costs
    return out

def drawdown_pct_last_window(ts_df: pd.DataFrame, equity_usd: float, window_min: int = 30) -> float:
    """Return current drawdown over last window in PCT of equity (negative is loss)."""
    if equity_usd <= 0 or ts_df is None or ts_df.empty:
        return 0.0
    ts = ts_df.sort_values("event_ts").copy()
    cut = pd.Timestamp.utcnow().tz_localize("UTC") - pd.Timedelta(minutes=window_min)
    ts = ts[ts["event_ts"] >= cut]
    if ts.empty:
        return 0.0
    cur = float(ts["realized_pnl_cum"].iloc[-1])
    peak = float(ts["realized_pnl_cum"].max())
    dd = cur - peak  # ≤ 0
    return (dd / equity_usd) * 100.0
