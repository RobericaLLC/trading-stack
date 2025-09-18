from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer

from trading_stack.adapters.alpaca.feed import capture_trades
from trading_stack.core.schemas import Bar1s
from trading_stack.ingest.aggregators import aggregate_trades_to_1s_bars
from trading_stack.ingest.metrics import freshness_p99_ms, rth_gap_events
from trading_stack.storage.parquet_store import write_events

app = typer.Typer(help="feedd: data ingest (synthetic + live adapters)")

@app.command("synthetic")
def synthetic(symbol: str = "SPY", minutes: int = 1, out: str = "data/synth_bars.parquet") -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    bars: list[Bar1s] = []
    px = 500.0
    for i in range(minutes * 60):
        ts = now + timedelta(seconds=i)
        drift = random.gauss(0, 0.02)
        px = max(1.0, px + drift)
        high = px + abs(random.gauss(0, 0.05))
        low = px - abs(random.gauss(0, 0.05))
        vol = max(1, int(abs(random.gauss(50, 20))))
        bars.append(Bar1s(ts=ts, symbol=symbol, open=px, high=high, low=low, close=px, volume=vol))
    write_events(out, bars)
    typer.echo(f"Wrote {len(bars)} synthetic bars to {out}")

@app.command("live-alpaca")
def live_alpaca(
    symbol: str = typer.Option("SPY", help="Ticker (US equities)"),
    minutes: int = typer.Option(5, help="Capture duration"),
    feed: str = typer.Option("v2/iex", help="v2/iex, v2/sip, or v2/test"),
    out_dir: str = typer.Option("data/live", help="Root dir for captures"),
) -> None:
    """Capture live trades via Alpaca WS, aggregate to 1s bars, persist Parquet, print SLOs."""
    trades = capture_trades(symbol=symbol, minutes=minutes, feed=feed)
    bars = aggregate_trades_to_1s_bars(trades, symbol=symbol)

    day = (trades[0].ts if trades else datetime.now(UTC)).date().isoformat()
    root = Path(out_dir) / day
    root.mkdir(parents=True, exist_ok=True)
    trades_path = root / f"trades_{symbol}.parquet"
    bars_path = root / f"bars1s_{symbol}.parquet"

    write_events(trades_path, trades)
    write_events(bars_path, bars)

    f99 = freshness_p99_ms(trades)
    gaps = rth_gap_events(trades, max_gap_sec=2)
    typer.echo(f"[live-alpaca] Captured trades={len(trades)}, bars={len(bars)}")
    typer.echo(f"[SLO] freshness_p99_ms={f99:.1f}  rth_gap_events={gaps}")