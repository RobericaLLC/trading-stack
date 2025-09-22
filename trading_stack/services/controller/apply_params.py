from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import typer

from trading_stack.accounting.realized import drawdown_pct_last_window, realized_pnl_timeseries
from trading_stack.params.runtime import RuntimeParams, append_applied

app = typer.Typer(help="Apply LLM proposals to runtime params with strict guardrails.")

def _now() -> datetime:
    return datetime.now(UTC)

def _read_latest_proposals(proposals_path: Path, lookback_min: int = 15) -> pd.DataFrame:
    if not proposals_path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(proposals_path)
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    cut = pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=lookback_min)
    return df[df["ts"] >= cut]

def _feed_health_ok(live_root: Path, symbol: str) -> bool:
    days = [p for p in live_root.glob("*") if p.is_dir()]
    if not days:
        return False
    day = days[-1]
    now = pd.Timestamp.utcnow().tz_localize("UTC")

    bars_path = day / f"bars1s_{symbol}.parquet"
    trades_path = day / f"trades_{symbol}.parquet"

    bars_ok = False
    if bars_path.exists():
        dfb = pd.read_parquet(bars_path)
        if not dfb.empty:
            dfb["ts"] = pd.to_datetime(dfb["ts"], utc=True).sort_values()
            age = (now - dfb["ts"].iloc[-1]).total_seconds()
            last_min = dfb[dfb["ts"] >= (now - pd.Timedelta(seconds=60))]
            coverage = len(last_min) / 60.0
            bars_ok = (age <= 60.0) and (coverage >= 0.50)

    trades_ok = False
    if trades_path.exists():
        dft = pd.read_parquet(trades_path)
        if not dft.empty:
            tcol = "ingest_ts" if "ingest_ts" in dft.columns else "ts"
            dft[tcol] = pd.to_datetime(dft[tcol], utc=True)
            dft = dft.sort_values(tcol)
            age = (now - dft[tcol].iloc[-1]).total_seconds()
            last_min = dft[dft[tcol] >= (now - pd.Timedelta(seconds=60))]
            trades_ok = (age <= 10.0) and (len(last_min) >= 20)  # flexible for IEX

    return bars_ok or trades_ok

def _pnl_freeze_ok(
    ledger_root: Path, symbol: str, window_min: int = 30, freeze_dd_pct: float = -0.5
) -> bool:
    """
    Return True if NOT frozen by P&L logic.
    - If there isn't enough realized P&L data in the window, return True (neutral).
    - Otherwise freeze if drawdown <= threshold.
    """
    today = _now().date().isoformat()
    ledger_path = Path(ledger_root) / today / "ledger.parquet"
    ts = realized_pnl_timeseries(ledger_path, symbol)
    if ts.empty:
        return True  # neutral: no realized data yet
    # keep only recent window
    ts = ts.sort_values("event_ts")
    cut = pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=window_min)
    tsw = ts[ts["event_ts"] >= cut]
    if tsw.shape[0] < 10:  # not enough signal yet → neutral
        return True
    equity = float(os.environ.get("EQUITY_USD", "30000"))
    dd_pct = drawdown_pct_last_window(tsw, equity_usd=equity, window_min=window_min)
    return dd_pct > float(freeze_dd_pct)

def _rate_limiter_ok(
    applied_path: Path, proposals_path: Path, max_accept_rate: float = 0.30, window_min: int = 15
) -> bool:
    cut = pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=window_min)
    applied = 0
    if applied_path.exists():
        dfa = pd.read_parquet(applied_path)
        if not dfa.empty:
            dfa["ts"] = pd.to_datetime(dfa["ts"], utc=True)
            applied = int(dfa[(dfa["ts"] >= cut) & (dfa["delta_bps"].abs() > 0)].shape[0])
    seen = 0
    if proposals_path.exists():
        dfp = pd.read_parquet(proposals_path)
        if not dfp.empty:
            dfp["ts"] = pd.to_datetime(dfp["ts"], utc=True)
            seen = int(dfp[dfp["ts"] >= cut].shape[0])
    if seen == 0:
        return True
    return (applied / seen) <= max_accept_rate

@app.command()
def main(
    symbol: str = "SPY",
    llm_root: str = "data/llm",
    live_root: str = "data/live",
    ledger_root: str = "data/exec",
    params_root: str = "data/params",
    interval_sec: float = 5.0,
    delta_cap_bps: float = 0.2,
    min_bps: float = 0.3,
    max_bps: float = 3.0,
) -> None:
    day = _now().date().isoformat()
    proposals_path = Path(llm_root) / day / f"proposals_{symbol}.parquet"
    applied_path = Path(llm_root) / day / f"applied_{symbol}.parquet"
    params_path = Path(params_root) / f"runtime_{symbol}.json"

    rp = RuntimeParams.load(params_path, symbol)

    while True:
        # Guards
        healthy = _feed_health_ok(Path(live_root), symbol)
        not_frozen = _pnl_freeze_ok(Path(ledger_root), symbol)
        rate_ok = _rate_limiter_ok(
            applied_path, proposals_path, max_accept_rate=0.30, window_min=15
        )
        freeze = not (healthy and not_frozen and rate_ok)

        df = _read_latest_proposals(proposals_path, lookback_min=15)
        seen = len(df)
        if seen == 0:
            time.sleep(interval_sec)
            continue

        last = df.sort_values("ts").iloc[-1]
        proposed = float(last.get("signal.threshold_bps", rp.signal_threshold_bps))

        # Bounds + delta cap
        proposed = min(max(proposed, min_bps), max_bps)
        cur = rp.signal_threshold_bps
        delta = proposed - cur
        if abs(delta) > delta_cap_bps:
            proposed = cur + (delta_cap_bps if delta > 0 else -delta_cap_bps)
            delta = proposed - cur

        if not freeze and abs(delta) > 0:
            rp.signal_threshold_bps = round(proposed, 3)
            rp.save(params_path)
            append_applied(
                applied_path,
                {
                    "ts": _now().isoformat(),
                    "symbol": symbol,
                    "accepted_threshold_bps": rp.signal_threshold_bps,
                    "delta_bps": round(delta, 3),
                    "seen": seen,
                    "freeze": False,
                },
            )
        else:
            # Log a no-op decision to preserve seen count + freeze status
            append_applied(
                applied_path,
                {
                    "ts": _now().isoformat(),
                    "symbol": symbol,
                    "accepted_threshold_bps": rp.signal_threshold_bps,
                    "delta_bps": 0.0,
                    "seen": seen,
                    "freeze": True,
                },
            )
        time.sleep(interval_sec)

if __name__ == "__main__":
    app()
