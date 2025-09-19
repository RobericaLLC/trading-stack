"""Engine live daemon - consumes bars and emits order intents."""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import typer

from trading_stack.core.schemas import Bar1s
from trading_stack.engine.decision_engine import DecisionEngine
from trading_stack.ipc.sqlite_queue import connect, enqueue
from trading_stack.storage.ledger import append_ledger

app = typer.Typer()


@app.command()
def main(
    symbol: str = "SPY",
    bars_dir: str = "data/live",
    queue: str = "data/queue.db",
    poll_sec: float = 1.0,
    shadow_ledger_root: str = "data/exec"
) -> None:
    """Run engine live loop, tailing bars and emitting order intents."""
    con = connect(queue)
    eng = DecisionEngine(symbol=symbol, threshold=0.5, max_notional=2000, price_band_bps=150)
    last_ts = None
    
    typer.echo(f"Starting engine live daemon for {symbol}, tailing {bars_dir}")
    typer.echo(f"Queue: {queue}, poll interval: {poll_sec}s")

    def latest_bars_path() -> str | None:
        """Find the latest bars file for today."""
        days = sorted([p for p in Path(bars_dir).glob("*") if p.is_dir()])
        return str(days[-1] / f"bars1s_{symbol}.parquet") if days else None

    while True:
        try:
            p = latest_bars_path()
            if p and Path(p).exists():
                df = pd.read_parquet(p)
                df["ts"] = pd.to_datetime(df["ts"], utc=True)
                df = df.sort_values("ts")
                
                # Process only new bars
                new = df if last_ts is None else df[df["ts"] > last_ts]
                
                for _, r in new.iterrows():
                    bar = Bar1s.model_validate(r.to_dict())
                    intents = eng.on_bar(bar)
                    
                    for o in intents:
                        # Generate idempotent tag
                        tag = o.tag or f"{o.ts:%Y%m%dT%H%M%S}_{o.symbol}_{o.side}_{int(o.qty)}"
                        payload = json.loads(o.model_dump_json())
                        
                        # Enqueue intent
                        enqueue(con, "order_intents", tag, payload)
                        
                        # Write shadow ledger entry
                        shadow_ts = datetime.now(UTC)
                        day = shadow_ts.date().isoformat()
                        shadow_path = f"{shadow_ledger_root}/{day}/ledger.parquet"
                        append_ledger(shadow_path, [{
                            "ts": shadow_ts,
                            "kind": "INTENT_SHADOW",
                            "tag": tag,
                            "symbol": o.symbol,
                            "side": o.side,
                            "qty": o.qty,
                            "limit": o.limit
                        }])
                        
                        typer.echo(f"Enqueued intent: {tag}")
                    
                    last_ts = bar.ts
                    
        except Exception as e:
            typer.echo(f"Error processing bars: {e}", err=True)
            
        time.sleep(poll_sec)


if __name__ == "__main__":
    app()
