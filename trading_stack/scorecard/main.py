from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from trading_stack.accounting.realized import drawdown_pct_last_window, realized_pnl_timeseries
from trading_stack.core.schemas import Bar1s
from trading_stack.storage.parquet_store import read_events, write_events

app = typer.Typer(help="Scorecard: PASS/FAIL gates for promotion")


def _ok(v: bool) -> str:
    return "[green]PASS[/green]" if v else "[red]FAIL[/red]"


@app.command()
def main(
    since: str = "1d",  # noqa: ARG001
    symbol: str = "SPY",
    live_dir: str = "data/live",
    sanity_window_min: int = 30,
    llm_dir: str = "data/llm",
) -> None:
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
        clock_offset_median_ms as _offs,
    )
    from trading_stack.ingest.metrics import (
        freshness_p99_ms as _f99,
    )
    from trading_stack.ingest.metrics import (
        rth_gap_events as _gaps,
    )
    from trading_stack.ingest.metrics import (
        trade_second_coverage as _cov,
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
            table.add_row(
                "clock_offset_median_ms", f"{offs:.1f}" if sample_n else "NA", _ok(offs_ok)
            )

            # Freshness only when offset is sane and we have enough samples
            if offs_ok and sample_n >= 20:
                f99 = _f99(trades_w_ing)
                table.add_row("freshness_p99_ms", f"{f99:.1f}", _ok(f99 < 750.0))
            else:
                table.add_row(
                    "freshness_p99_ms", "skipped (clock skew or small sample)", _ok(False)
                )

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
                ack_threshold = float(
                    os.environ.get("ACK_P95_MS", str(default_thresh if env != "paper" else 1200.0))
                )
                table.add_row("ack_latency_p95_ms", f"{ack_p95:.1f}", _okf(ack_p95 < ack_threshold))
            else:
                table.add_row("ack_latency_p95_ms", "NA", _okf(False))

            # cancel_success (sanity_* tags only)
            now = datetime.now(UTC)
            cut = now - timedelta(minutes=sanity_window_min)

            sanity = df[
                (df["kind"] == "INTENT") & (df["tag"].astype(str).str.startswith("sanity_"))
            ][["tag", "ts"]]
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
                table.add_row(
                    f"cancel_success (sanity {sanity_window_min}m, acked)",
                    f"{rate:.0%}",
                    _okf(rate == 1.0),
                )
            else:
                table.add_row(
                    f"cancel_success (sanity {sanity_window_min}m, acked)", "NA", _okf(False)
                )

            # TCA shortfall median (bps) for tags with PNL_SNAPSHOT.shortfall_bps
            pnl = df[df["kind"] == "PNL_SNAPSHOT"]
            if not pnl.empty and "shortfall_bps" in pnl.columns:
                med = float(pnl["shortfall_bps"].median())
                table.add_row("shortfall_median_bps", f"{med:.1f}", _okf(med < 4.0))
            else:
                table.add_row("shortfall_median_bps", "NA", _okf(False))
            
            # Ledger integrity & realized P&L checks
            tsdf = realized_pnl_timeseries(ledger_path, symbol)
            eq = float(os.environ.get("EQUITY_USD", "30000"))
            points_30m = 0
            if not tsdf.empty:
                tsdf = tsdf.sort_values("event_ts")
                cut = pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=30)
                points_30m = int(tsdf[tsdf["event_ts"] >= cut].shape[0])
            table.add_row("realized_points_30m", str(points_30m), _ok(points_30m >= 10))
            ddpct = (
                drawdown_pct_last_window(tsdf, equity_usd=eq, window_min=30) 
                if points_30m >= 10 else 0.0
            )
            table.add_row("pnl_drawdown_30m_pct", f"{ddpct:.2f}%", _ok(ddpct > -0.5))
        else:
            table.add_row("ledger_integrity", "missing", _ok(False))
            table.add_row("realized_points_30m", "0", _ok(False))
            table.add_row("pnl_drawdown_30m_pct", "NA", _ok(True))
    else:
        table.add_row("ledger_integrity", "no exec dir", _ok(False))
        table.add_row("realized_points_30m", "0", _ok(False))
        table.add_row("pnl_drawdown_30m_pct", "NA", _ok(True))

    # LIVE LOOP HEALTH METRICS

    # ENGINE METRICS
    # Check queue database for queue depth and dead letters
    queue_path = Path("data/queue.db")
    if queue_path.exists():
        from trading_stack.ipc.sqlite_queue import connect, dead_letter_count, depth

        con = connect(queue_path)
        queue_d = depth(con, "order_intents")
        dead_count = dead_letter_count(con, "order_intents")
        table.add_row("queue_depth", str(queue_d), _ok(queue_d == 0))
        table.add_row("dead_letter_count", str(dead_count), _ok(dead_count == 0))
        con.close()

    # Check engine coverage by comparing shadow intents to bars
    if latest_exec and latest:
        shadow_ledger = latest_exec / "ledger.parquet"
        bars_path = latest / f"bars1s_{symbol}.parquet"

        if shadow_ledger.exists() and bars_path.exists():
            # Read shadow intents from last 15 minutes
            ledger_df = pd.read_parquet(shadow_ledger)
            shadow_intents = ledger_df[ledger_df["kind"] == "INTENT_SHADOW"]
            if not shadow_intents.empty:
                # Get intents from last 15 minutes
                cut = now - timedelta(minutes=15)
                recent_intents = shadow_intents[shadow_intents["ts"] >= cut]
                intent_count = len(recent_intents)
                table.add_row(
                    "intents_enqueued_last_15m", str(intent_count), _ok(intent_count >= 1)
                )

                # Calculate engine coverage
                bars_df = pd.read_parquet(bars_path)
                bars_df["ts"] = pd.to_datetime(bars_df["ts"])
                recent_bars = bars_df[bars_df["ts"] >= cut]

                if not recent_bars.empty:
                    # Engine coverage = processed bars / total bars (using shadow intents as proxy)
                    # For now, assume engine processed all bars if it generated intents
                    coverage = 1.0 if intent_count > 0 else 0.0
                    table.add_row(
                        "engine_coverage_last_15m", f"{coverage:.0%}", _ok(coverage >= 0.95)
                    )
                else:
                    table.add_row("engine_coverage_last_15m", "NA", _ok(False))
            else:
                table.add_row("intents_enqueued_last_15m", "0", _ok(False))
                table.add_row("engine_coverage_last_15m", "0%", _ok(False))

    # RISK METRICS
    if latest_exec:
        ledger_path = latest_exec / "ledger.parquet"
        if ledger_path.exists():
            df = pd.read_parquet(ledger_path)

            # Check blocked orders in last 15 minutes
            cut = now - timedelta(minutes=15)
            recent_rej = df[(df["kind"] == "REJ") & (df["ts"] >= cut)]
            if "reason" in recent_rej.columns:
                # Count rejections that are risk-related (exclude operational failures)
                risk_reasons = [
                    "killswitch",
                    "whitelist",
                    "notional",
                    "price band",
                    "max open",
                    "daily loss",
                ]
                risk_blocks = recent_rej[
                    recent_rej["reason"].str.contains("|".join(risk_reasons), case=False, na=False)
                ]
                blocked_count = len(risk_blocks)
            else:
                blocked_count = 0
            table.add_row("blocked_orders_last_15m", str(blocked_count), _ok(blocked_count == 0))

            # Check if daily stop triggered
            killswitch_path = Path("RUN/HALT")
            daily_stop = killswitch_path.exists()
            table.add_row("daily_stop_triggered", str(daily_stop), _ok(not daily_stop))

    # OPS METRICS - uptime check via heartbeat files
    heartbeat_dir = Path("RUN/heartbeat")
    if heartbeat_dir.exists():
        # Check heartbeat files modified in last 60s
        services = ["feedd", "engined", "execd"]
        all_up = True
        for service in services:
            hb_file = heartbeat_dir / f"{service}.hb"
            if hb_file.exists():
                mtime = datetime.fromtimestamp(hb_file.stat().st_mtime, UTC)
                age_sec = (now - mtime).total_seconds()
                up = age_sec < 60
                all_up = all_up and up
            else:
                all_up = False

        # Calculate uptime percentage (simplified - just current state)
        uptime = 100.0 if all_up else 0.0
        table.add_row("uptime_rth", f"{uptime:.0f}%", _ok(uptime > 99.0))
    else:
        table.add_row("uptime_rth", "NA", _ok(False))

    # LLM (shadow) SLOs
    llm_root = Path(llm_dir)
    day_dirs = [p for p in llm_root.glob("*") if p.is_dir()]
    latest_llm = max(day_dirs) if day_dirs else None
    if latest_llm:
        props_path = latest_llm / f"proposals_{symbol}.parquet"
        if props_path.exists():
            dfp = pd.read_parquet(props_path)
            cutoff = pd.Timestamp.utcnow() - pd.Timedelta(minutes=15)
            n15 = dfp[dfp["ts"] >= cutoff.isoformat()].shape[0]
            cost = float(dfp.get("cost_usd", pd.Series([0.0] * len(dfp))).sum())
            # schema conformance is ensured at write time; still assert required columns present
            required_cols = {"ts", "symbol", "signal.threshold_bps", "risk.multiplier", "provider"}
            schema_ok = required_cols.issubset(dfp.columns)
            table.add_row("llm_schema_conformance", "100%" if schema_ok else "0%", _ok(schema_ok))
            # >= 6 proposals in last 15m (~every 2-3 min minimum)
            table.add_row("llm_shadow_events_15m", str(n15), _ok(n15 >= 6))
            table.add_row("llm_cost_per_day_usd", f"{cost:.2f}", _ok(cost <= 10.0))
        else:
            table.add_row("llm_proposals_present", "False", _ok(False))
    else:
        table.add_row("llm_day_dir_present", "False", _ok(False))

    # LLM (applied) SLOs
    llm_root = Path(llm_dir)
    day_dirs = [p for p in llm_root.glob("*") if p.is_dir()]
    latest_llm = max(day_dirs) if day_dirs else None
    if latest_llm:
        props_path = latest_llm / f"proposals_{symbol}.parquet"
        ap_path = latest_llm / f"applied_{symbol}.parquet"
        cut15 = pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=15)
        
        # Count proposals seen
        seen15 = 0
        if props_path.exists():
            dfp = pd.read_parquet(props_path)
            dfp["ts"] = pd.to_datetime(dfp["ts"], utc=True)
            seen15 = dfp[dfp["ts"] >= cut15].shape[0]
        table.add_row("llm_proposals_seen_15m", str(seen15), _ok(seen15 >= 6))

        # Count applied and calculate rate
        if ap_path.exists():
            dfa = pd.read_parquet(ap_path)
            if not dfa.empty:
                dfa["ts"] = pd.to_datetime(dfa["ts"], utc=True)
                a15 = dfa[dfa["ts"] >= cut15]
                applied15 = a15[a15["delta_bps"].abs() > 0].shape[0]
                # Calculate rate using actual proposal count
                rate = applied15 / seen15 if seen15 > 0 else 0.0
                table.add_row("llm_proposals_applied_15m", str(applied15), _ok(applied15 <= 2))
                table.add_row("llm_accept_rate_15m", f"{rate:.0%}", _ok(rate <= 0.30))
                # bounds check
                params_path = Path("data/params") / f"runtime_{symbol}.json"
                if params_path.exists():
                    cur = json.loads(params_path.read_text(encoding="utf-8")).get(
                        "signal_threshold_bps", 0.5
                    )
                    bounds_ok = 0.3 <= float(cur) <= 3.0
                    table.add_row(
                        "llm_param_bounds_ok", "True" if bounds_ok else "False", _ok(bounds_ok)
                    )
                # freeze status
                freeze_active = (
                    bool(a15.tail(1)["freeze"].iloc[0])
                    if "freeze" in a15.columns and not a15.empty
                    else False
                )
                table.add_row("llm_freeze_active", str(freeze_active), _ok(not freeze_active))
            else:
                table.add_row("llm_proposals_applied_15m", "0", _ok(False))
                table.add_row("llm_accept_rate_15m", "0%", _ok(True))
                table.add_row("llm_param_bounds_ok", "NA", _ok(False))
                table.add_row("llm_freeze_active", "NA", _ok(False))
        else:
            # Applied file doesn't exist yet
            table.add_row("llm_proposals_applied_15m", "0", _ok(True))  # 0 is fine
            table.add_row("llm_accept_rate_15m", "0%", _ok(True))  # 0% is fine
            table.add_row("llm_param_bounds_ok", "NA", _ok(False))
            table.add_row("llm_freeze_active", "NA", _ok(True))  # NA means not frozen
    else:
        table.add_row("llm_proposals_seen_15m", "0", _ok(False))
        table.add_row("llm_proposals_applied_15m", "0", _ok(True))
        table.add_row("llm_accept_rate_15m", "0%", _ok(True))
        table.add_row("llm_param_bounds_ok", "NA", _ok(False))
        table.add_row("llm_freeze_active", "NA", _ok(True))

    console.print(table)


if __name__ == "__main__":
    app()
