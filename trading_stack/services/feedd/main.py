from __future__ import annotations
import typer
from datetime import datetime, timedelta, timezone
import random
from trading_stack.core.schemas import Bar1s
from trading_stack.storage.parquet_store import write_events

app = typer.Typer(help="feedd: data ingest (synthetic mode in scaffold)")

@app.command()
def main(mode: str = typer.Option("synthetic", help="synthetic only in scaffold"),
         symbol: str = "SPY",
         minutes: int = 1,
         out: str = "data/synth_bars.parquet"):
    assert mode == "synthetic", "Scaffold supports only synthetic mode"
    now = datetime.now(timezone.utc).replace(microsecond=0)
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

if __name__ == "__main__":
    app()
