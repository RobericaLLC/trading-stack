from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import typer

from trading_stack.accounting.positions import write_snapshot

app = typer.Typer(help="Positions & PnL snapshot from ledger")

@app.command()
def main(ledger_root: str = "data/exec", out_root: str = "data/accounting") -> None:
    today = datetime.now(UTC).date().isoformat()
    led = Path(ledger_root) / today / "ledger.parquet"
    out_dir = Path(out_root) / today
    out_dir.mkdir(parents=True, exist_ok=True)
    write_snapshot(led, out_dir / "positions.parquet")
    typer.echo(f"[accounting] wrote {out_dir / 'positions.parquet'}")

if __name__ == "__main__":
    app()
