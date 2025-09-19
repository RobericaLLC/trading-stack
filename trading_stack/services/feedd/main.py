from __future__ import annotations

import asyncio
import json
import os
import random
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer

from trading_stack.adapters.alpaca.feed import capture_trades
from trading_stack.core.schemas import Bar1s, MarketTrade
from trading_stack.ingest.aggregators import aggregate_trades_to_1s_bars
from trading_stack.ingest.metrics import freshness_p99_ms, rth_gap_events
from trading_stack.storage.parquet_store import read_events, write_events

app = typer.Typer(help="feedd: data ingest (synthetic + live adapters)")


def _run_continuous_capture(symbol: str, feed: str, out_dir: str, flush_interval: int) -> None:
    """Run continuous capture with periodic Parquet flushes."""
    try:
        import websockets
    except ImportError:
        raise RuntimeError("websockets not installed. pip install websockets") from None
    
    typer.echo(
        f"[live-alpaca] Starting continuous capture for {symbol}, "
        f"flush every {flush_interval}s"
    )
    
    key = os.environ.get("ALPACA_API_KEY_ID")
    secret = os.environ.get("ALPACA_API_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError("Set ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY in environment")
    
    async def run() -> None:
        from trading_stack.adapters.alpaca.feed import BASE, _iso_to_dt
        
        uri = f"{BASE}/{feed}"
        buffer_trades: list[MarketTrade] = []
        last_flush = time.time()
        
        async with websockets.connect(uri, ping_interval=15, ping_timeout=10) as ws:
            # Authenticate
            await ws.send(json.dumps({"action": "auth", "key": key, "secret": secret}))
            # Subscribe to trades
            await ws.send(json.dumps({"action": "subscribe", "trades": [symbol]}))
            
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    now = datetime.now(UTC)
                    payload = json.loads(raw)
                    events = payload if isinstance(payload, list) else [payload]
                    
                    for ev in events:
                        if ev.get("T") == "t":  # trade event
                            ts = _iso_to_dt(ev["t"])
                            trade = MarketTrade(
                                ts=ts,
                                symbol=str(ev["S"]),
                                price=float(ev["p"]),
                                size=int(ev["s"]),
                                venue=None,
                                source=f"alpaca:{feed}",
                                ingest_ts=now,
                            )
                            buffer_trades.append(trade)
                            
                except TimeoutError:
                    pass
                
                # Check if we should flush
                if time.time() - last_flush >= flush_interval and buffer_trades:
                    # Aggregate to bars
                    bars = aggregate_trades_to_1s_bars(buffer_trades, symbol=symbol)
                    
                    # Write to today's directory
                    day = datetime.now(UTC).date().isoformat()
                    root = Path(out_dir) / day
                    root.mkdir(parents=True, exist_ok=True)
                    
                    trades_path = root / f"trades_{symbol}.parquet"
                    bars_path = root / f"bars1s_{symbol}.parquet"
                    
                    # Append to existing files
                    existing_trades = []
                    existing_bars = []
                    if trades_path.exists():
                        existing_trades = read_events(str(trades_path), MarketTrade)
                    if bars_path.exists():
                        existing_bars = read_events(str(bars_path), Bar1s)
                    
                    # Combine and write
                    all_trades = existing_trades + buffer_trades
                    all_bars = existing_bars + bars
                    
                    write_events(trades_path, all_trades)
                    write_events(bars_path, all_bars)
                    
                    # Calculate and print metrics
                    f99 = freshness_p99_ms(buffer_trades)
                    gaps = rth_gap_events(buffer_trades, max_gap_sec=2)
                    typer.echo(f"[flush] trades={len(buffer_trades)}, bars={len(bars)}, "
                             f"freshness_p99_ms={f99:.1f}, gaps={gaps}")
                    
                    # Clear buffer
                    buffer_trades = []
                    last_flush = time.time()
    
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        typer.echo("\n[live-alpaca] Stopped by user")

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
    minutes: int = typer.Option(5, help="Capture duration (0 for continuous)"),
    feed: str = typer.Option("v2/iex", help="v2/iex, v2/sip, or v2/test"),
    out_dir: str = typer.Option("data/live", help="Root dir for captures"),
    flush_interval: int = typer.Option(60, help="Flush interval in seconds for continuous mode"),
) -> None:
    """Capture live trades via Alpaca WS, aggregate to 1s bars, persist Parquet, print SLOs."""
    if minutes == 0:
        # Continuous mode with periodic flushes
        _run_continuous_capture(symbol, feed, out_dir, flush_interval)
    else:
        # Fixed duration capture
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