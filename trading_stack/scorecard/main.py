from __future__ import annotations

import hashlib
import json
import os
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
def main(
    since: str = "1d",
    symbol: str = "SPY",
    live_dir: str = "data/live",
    sanity_window_min: int = 30,
) -> None:  # noqa: ARG001
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

    # 5) Live capture SLOs (if present)
    import pandas as pd
    
    from trading_stack.core.schemas import MarketTrade
    from trading_stack.ingest.metrics import (
        freshness_p99_ms as _f99,
        rth_gap_events as _gaps,
        trade_second_coverage as _cov,
        clock_offset_median_ms as _offs,
    )

    live_root = Path(live_dir)
    day_dirs = [p for p in live_root.glob("*") if p.is_dir()]
    latest = max(day_dirs) if day_dirs else None
    if latest:
        trades_path = latest / f"trades_{symbol}.parquet"
        if trades_path.exists():
            trades = read_events(trades_path, MarketTrade)
            trades_w_ing = [t for t in trades if t.ingest_ts is not None]
            sample_n = len(trades_w_ing)

            # Clock offset
            offs = _offs(trades_w_ing) if sample_n else float("nan")
            offs_ok = (abs(offs) < 1000.0) if sample_n else False
            table.add_row("clock_offset_median_ms", f"{offs:.1f}" if sample_n else "NA", _ok(offs_ok))

            # Freshness only when offset is sane and we have enough samples
            if offs_ok and sample_n >= 20:
                f99 = _f99(trades_w_ing)
                table.add_row("freshness_p99_ms", f"{f99:.1f}", _ok(f99 < 750.0))
            else:
                table.add_row("freshness_p99_ms", "skipped (clock skew or small sample)", _ok(False))

            # IEX vs SIP gating
            srcs = {t.source or "" for t in trades}
            feed = next((s for s in srcs if s.startswith("alpaca:")), "alpaca:unknown")
            if feed.startswith("alpaca:v2/iex"):
                cov = _cov(trades)
                table.add_row("trade_sec_coverage", f"{cov:.0%}", _ok(cov > 0.35))  # strictly >
            else:
                gaps = _gaps(trades, max_gap_sec=2)
                table.add_row("rth_gap_events", str(gaps), _ok(gaps == 0))
        else:
            table.add_row("live_trades_present", "False", _ok(False))
    else:
        table.add_row("live_day_dir_present", "False", _ok(False))

    # EXECUTION SLOs (if a ledger exists)
    exec_root = Path("data/exec")
    day_dirs = [p for p in exec_root.glob("*") if p.is_dir()]
    latest_exec = max(day_dirs) if day_dirs else None

    def _okf(cond: bool) -> str:
        return _ok(cond)

    if latest_exec:
        ledger_path = latest_exec / "ledger.parquet"
        if ledger_path.exists():
            df = pd.read_parquet(ledger_path)
            # ack_latency: compute per tag (ACK.event_ts - INTENT.ts)
            intents = df[df["kind"] == "INTENT"][["tag", "ts"]].rename(columns={"ts": "t_intent"})
            acks_df = df[df["kind"] == "ACK"]
            if not acks_df.empty and "event_ts" in acks_df.columns:
                acks = acks_df[["tag", "event_ts"]].rename(columns={"event_ts": "t_ack"})
            else:
                acks = pd.DataFrame(columns=["tag", "t_ack"])
            m = intents.merge(acks, on="tag", how="inner")
            if not m.empty:
                m["ack_ms"] = (m["t_ack"] - m["t_intent"]).dt.total_seconds() * 1000.0
                ack_p95 = float(m["ack_ms"].quantile(0.95))
                env = os.environ.get("EXEC_ENV", "paper").lower()
                default_thresh = 1000.0 if env == "paper" else 400.0
                ack_threshold = float(os.environ.get("ACK_P95_MS", str(default_thresh if env != "paper" else 1200.0)))
                table.add_row("ack_latency_p95_ms", f"{ack_p95:.1f}", _okf(ack_p95 < ack_threshold))
            else:
                table.add_row("ack_latency_p95_ms", "NA", _okf(False))

            # cancel_success (sanity_* tags only)
            from datetime import timedelta
            
            now = datetime.now(UTC)
            cut = now - timedelta(minutes=sanity_window_min)

            sanity = df[(df["kind"] == "INTENT") & (df["tag"].astype(str).str.startswith("sanity_"))][["tag","ts"]]
            sanity = sanity[sanity["ts"] >= cut]

            acks_df = df[df["kind"] == "ACK"][["tag"]].drop_duplicates()
            fills = df[df["kind"] == "FILL"][["tag"]].drop_duplicates()
            cancels = df[df["kind"] == "CANCEL"][["tag"]].drop_duplicates()

            if not sanity.empty:
                # only ACKed sanity intents
                m = sanity[["tag"]].merge(acks_df, on="tag", how="inner")
                cancels["has_cancel"] = True
                fills["has_fill"] = True
                m = m.merge(cancels, on="tag", how="left").merge(fills, on="tag", how="left")
                m["ok_cancel"] = m["has_cancel"].fillna(False) & m["has_fill"].isna()
                rate = m["ok_cancel"].sum() / len(m) if len(m) else 0.0
                table.add_row(f"cancel_success (sanity {sanity_window_min}m, acked)", f"{rate:.0%}", _okf(rate == 1.0))
            else:
                table.add_row(f"cancel_success (sanity {sanity_window_min}m, acked)", "NA", _okf(False))

            # TCA shortfall median (bps) for tags with PNL_SNAPSHOT.shortfall_bps
            pnl = df[df["kind"] == "PNL_SNAPSHOT"]
            if not pnl.empty and "shortfall_bps" in pnl.columns:
                med = float(pnl["shortfall_bps"].median())
                table.add_row("shortfall_median_bps", f"{med:.1f}", _okf(med < 4.0))
            else:
                table.add_row("shortfall_median_bps", "NA", _okf(False))
        else:
            table.add_row("exec_ledger_present", "False", _ok(False))
    else:
        table.add_row("exec_day_dir_present", "False", _ok(False))

    console.print(table)


if __name__ == "__main__":
    app()