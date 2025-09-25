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
from trading_stack.utils.env_loader import load_env

# Load environment variables on import
load_env()

app = typer.Typer()


def _load_runtime_threshold(params_root: str, symbol: str, default_bps: float = 0.5) -> float:
    p = Path(params_root) / f"runtime_{symbol}.json"
    if not p.exists():
        return default_bps
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return float(d.get("signal_threshold_bps", default_bps))
    except Exception:
        return default_bps


@app.command()
def main(
    symbol: str = "SPY",
    bars_dir: str = "data/live",
    queue: str = "data/queue.db",
    poll_sec: float = 1.0,
    shadow_ledger_root: str = "data/exec",
    params_root: str = "data/params",
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
                    
                    # Hot-reload threshold before each decision
                    th_bps = _load_runtime_threshold(params_root, symbol, default_bps=0.5)
                    eng.strategy.th = th_bps  # MeanReversion1S.th is in bps units
                    
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
                        shadow_path = f"{shadow_ledger_root}/{day}/shadow_ledger.parquet"
                        append_ledger(
                            shadow_path,
                            [
                                {
                                    "ts": shadow_ts,
                                    "kind": "INTENT_SHADOW",
                                    "tag": tag,
                                    "symbol": o.symbol,
                                    "side": o.side,
                                    "qty": o.qty,
                                    "limit": o.limit,
                                }
                            ],
                        )

                        typer.echo(f"Enqueued intent: {tag}")

                    last_ts = bar.ts

        except Exception as e:
            typer.echo(f"Error processing bars: {e}", err=True)

        # Update heartbeat
        from trading_stack.ops.heartbeat import beat
        beat("engined")
        
        time.sleep(poll_sec)


if __name__ == "__main__":
    app()
