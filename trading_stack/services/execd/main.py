from __future__ import annotations

from datetime import UTC, datetime

import typer

from trading_stack.core.schemas import NewOrder

app = typer.Typer(help="execd: broker adapter scaffold (no live routing in scaffold)")

@app.command()
def main() -> None:
    # Placeholder for live adapter. Demonstrates state-machine hook point.
    ts = datetime.now(UTC)
    ex = NewOrder(symbol="SPY", side="BUY", qty=1, limit=500.0, tag="demo", ts=ts)
    typer.echo(f"[DRY-RUN] Would submit order: {ex.model_dump_json()}")

if __name__ == "__main__":
    app()
