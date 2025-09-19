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
    cut = pd.Timestamp.utcnow().tz_localize("UTC") - pd.Timedelta(minutes=lookback_min)
    return df[df["ts"] >= cut]

def _feed_health_ok(live_root: Path, symbol: str) -> bool:
    # Lightweight: require bars for last minute.
    day_dirs = [p for p in live_root.glob("*") if p.is_dir()]
    if not day_dirs:
        return False
    bars_path = day_dirs[-1] / f"bars1s_{symbol}.parquet"
    if not bars_path.exists():
        return False
    df = pd.read_parquet(bars_path)
    if df.empty:
        return False
    df["ts"] = pd.to_datetime(df["ts"], utc=True).sort_values()
    recent = df[df["ts"] >= (pd.Timestamp.utcnow().tz_localize("UTC") - pd.Timedelta(seconds=60))]
    return len(recent) >= 30  # ~≥50% of seconds got bars in last minute on IEX; tune as needed

def _pnl_freeze_ok(
    ledger_root: Path, symbol: str, window_min: int = 30, freeze_dd_pct: float = -0.5
) -> bool:
    """Return True if NOT frozen (i.e., drawdown above threshold)."""
    today = _now().date().isoformat()
    ledger_path = Path(ledger_root) / today / "ledger.parquet"
    ts = realized_pnl_timeseries(ledger_path, symbol)
    equity = float(os.environ.get("EQUITY_USD", "30000"))
    dd_pct = drawdown_pct_last_window(ts, equity_usd=equity, window_min=window_min)
    # Freeze if drawdown ≤ threshold (e.g., ≤ -0.5%)
    return dd_pct > float(freeze_dd_pct)

def _rate_limiter_ok(
    applied_path: Path, max_accept_rate: float = 0.30, window_min: int = 15
) -> bool:
    if not applied_path.exists():
        return True
    df = pd.read_parquet(applied_path)
    if df.empty:
        return True
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    cut = pd.Timestamp.utcnow().tz_localize("UTC") - pd.Timedelta(minutes=window_min)
    df = df[df["ts"] >= cut]
    seen = int(df["seen"].sum()) if "seen" in df.columns else max(len(df)*3, 1)  # fallback
    applied = len(df)
    rate = applied / max(seen, 1)
    return rate <= max_accept_rate

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
        rate_ok = _rate_limiter_ok(applied_path, max_accept_rate=0.30, window_min=15)
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
