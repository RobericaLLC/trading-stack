from __future__ import annotations

import typer

from trading_stack.core.schemas import Bar1s
from trading_stack.engine.decision_engine import DecisionEngine
from trading_stack.storage.parquet_store import read_events

app = typer.Typer(help="engined: deterministic strategy loop (offline demo)")

@app.command()
def main(
    bars_path: str = "data/synth_bars.parquet",
    threshold: float = 0.5,
    max_notional: float = 2000,
    band_bps: int = 150
) -> None:
    bars = read_events(bars_path, Bar1s)
    eng = DecisionEngine(
        symbol="SPY",
        threshold=threshold,
        max_notional=max_notional,
        price_band_bps=band_bps
    )
    intents = 0
    for b in bars:
        orders = eng.on_bar(b)
        intents += len(orders)
    typer.echo(f"Processed {len(bars)} bars; generated {intents} order intents under risk gate.")

if __name__ == "__main__":
    app()
