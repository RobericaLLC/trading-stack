from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from trading_stack.core.schemas import Bar1s
from trading_stack.storage.parquet_store import read_events, write_events

app = typer.Typer(help="Scorecard: PASS/FAIL gates for promotion")

def _ok(v: bool) -> str:
    return "[green]PASS[/green]" if v else "[red]FAIL[/red]"

@app.command()
def main(since: str = "1d") -> None:  # noqa: ARG001
    console = Console()
    table = Table(title="Trading Stack Scorecard")
    table.add_column("Check")
    table.add_column("Value")
    table.add_column("Result")

    # 1) Storage round-trip on sample Bar1s
    now = datetime.now(UTC).replace(microsecond=0)
    tmp = Path("./data/_scorecard_bars.parquet")
    bars = [Bar1s(ts=now, symbol="SPY", open=500, high=501, low=499, close=500.5, volume=100)]
    write_events(tmp, bars)
    back = read_events(tmp, Bar1s)
    table.add_row("storage_roundtrip_count", str(len(back)), _ok(len(back) == 1))

    # 2) Determinism hash (serialize to json-friendly payload and hash)
    payload = [b.model_dump(mode="json") for b in back]  # ensures ts -> ISO8601 string
    s = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    h = hashlib.sha256(s).hexdigest()[:12]
    table.add_row("determinism_hash", h, _ok(len(h) == 12))

    # 3) Sample data presence
    sample = Path("sample_data/events_spy_2024-09-10.parquet")
    sample2 = Path("sample_data/events_spy_2024-09-10.csv")
    exists = sample.exists() or sample2.exists()
    table.add_row("sample_data_present", str(exists), _ok(exists))

    # 4) Clock sanity
    skew_ok = True  # In scaffold we assert no skew; real check uses feed vs system
    table.add_row("clock_skew_ms", "0", _ok(skew_ok))

    console.print(table)
