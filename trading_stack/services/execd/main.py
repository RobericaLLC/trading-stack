from __future__ import annotations
import typer
from trading_stack.core.schemas import NewOrder
from datetime import datetime, timezone

app = typer.Typer(help="execd: broker adapter scaffold (no live routing in scaffold)")

@app.command()
def main():
    # Placeholder for live adapter. Demonstrates state-machine hook point.
    ts = datetime.now(timezone.utc)
    ex = NewOrder(symbol="SPY", side="BUY", qty=1, limit=500.0, tag="demo", ts=ts)
    typer.echo(f"[DRY-RUN] Would submit order: {ex.model_dump_json()}")

if __name__ == "__main__":
    app()
