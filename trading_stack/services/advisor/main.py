from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

import typer

from trading_stack.llm.advisor import append_proposal, make_proposal

app = typer.Typer(help="LLM advisor (shadow). Emits strict-JSON param proposals; does NOT trade.")


@app.command()
def main(
    symbol: str = "SPY",
    bars_dir: str = "data/live",
    out_root: str = "data/llm",
    provider: str = "rules",
    interval_sec: float = 5.0,
    budget_usd: float = 10.0,
) -> None:
    day = datetime.now(UTC).date().isoformat()
    bars_path = Path(bars_dir) / day / f"bars1s_{symbol}.parquet"
    out_path = Path(out_root) / day / f"proposals_{symbol}.parquet"
    spent = 0.0
    while True:
        if spent >= budget_usd:
            typer.echo(
                f"[advisor] budget reached ${spent:.2f}/{budget_usd:.2f}. Sleeping 5 minutes."
            )
            time.sleep(300)
            continue
        if not bars_path.exists():
            time.sleep(interval_sec)
            continue
        proposal = make_proposal(symbol, bars_path, provider_kind=provider)
        # In shadow mode, cost is provider-dependent; RulesProvider costs 0.0
        cost = 0.0
        append_proposal(out_path, proposal, provider, cost)
        spent += cost
        time.sleep(interval_sec)


if __name__ == "__main__":
    app()
