# trading_stack/ops/status.py
from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd
import typer

from trading_stack.ingest.metrics import freshness_p99_ms, clock_offset_median_ms
from trading_stack.core.schemas import MarketTrade

app = typer.Typer(help="Ops status: single-line summary + verbose dashboard")

# ---------- helpers

def now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")

def _latest_day_dir(root: Path) -> Optional[Path]:
    days = sorted([p for p in root.glob("*") if p.is_dir()])
    return days[-1] if days else None

def _read_parquet_safe(p: Path) -> Optional[pd.DataFrame]:
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception:
        return None

def _format_pct(x: Optional[float]) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "NA"
    return f"{x:.0%}"

def _format_ms(x: Optional[float]) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "NA"
    return f"{x:.1f}ms"

def _format_s(x: Optional[float]) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "NA"
    return f"{x:.1f}s"

def _safe_dt_series(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, utc=True, errors="coerce")

# ---------- probes

@dataclass
class FeedProbe:
    bars_rows: int = 0
    bars_age_s: Optional[float] = None
    bars_cov_1m: Optional[float] = None
    trades_rows: int = 0
    trades_age_s: Optional[float] = None
    trades_1m: int = 0
    ingest_ratio: Optional[float] = None
    f99_ms: Optional[float] = None
    offs_ms: Optional[float] = None
    healthy: bool = False

def probe_feed(live_dir: Path, symbol: str, window_min: int = 1, cov_threshold: float = 0.50) -> FeedProbe:
    day = _latest_day_dir(live_dir)
    out = FeedProbe()
    if day is None:
        return out
    now = now_utc()

    bars_p = day / f"bars1s_{symbol}.parquet"
    trades_p = day / f"trades_{symbol}.parquet"

    # Bars
    dfb = _read_parquet_safe(bars_p)
    if dfb is not None and not dfb.empty and "ts" in dfb.columns:
        dfb["ts"] = _safe_dt_series(dfb["ts"])
        dfb = dfb.sort_values("ts")
        out.bars_rows = len(dfb)
        last = dfb["ts"].iloc[-1]
        out.bars_age_s = float((now - last).total_seconds())
        cut = now - pd.Timedelta(minutes=window_min)
        secs = dfb[dfb["ts"] >= cut]["ts"].dt.floor("s").nunique()
        out.bars_cov_1m = secs / float(60 * window_min)

    # Trades
    dft = _read_parquet_safe(trades_p)
    if dft is not None and not dft.empty:
        out.trades_rows = len(dft)
        tcol = "ingest_ts" if "ingest_ts" in dft.columns else ("ts" if "ts" in dft.columns else None)
        if "ingest_ts" in dft.columns:
            dft["ingest_ts"] = _safe_dt_series(dft["ingest_ts"])
            out.ingest_ratio = float(dft["ingest_ts"].notna().sum()) / max(len(dft), 1)
        if "ts" in dft.columns:
            dft["ts"] = _safe_dt_series(dft["ts"])
        if tcol is not None and dft[tcol].notna().any():
            dft = dft.sort_values(tcol)
            last_ing = dft[tcol].dropna().iloc[-1]
            out.trades_age_s = float((now - last_ing).total_seconds())
            cut = now - pd.Timedelta(minutes=window_min)
            out.trades_1m = int(dft[dft[tcol] >= cut].shape[0])

            # latency + clock offset if we have enough
            if "ingest_ts" in dft.columns:
                sample = dft[dft["ingest_ts"].notna()].tail(400)
                mts: list[MarketTrade] = []
                for _, r in sample.iterrows():
                    try:
                        mts.append(
                            MarketTrade(
                                ts=(r["ts"].to_pydatetime() if pd.notna(r["ts"]) else now.to_pydatetime()),
                                symbol=str(r.get("symbol", symbol)),
                                price=float(r.get("price", 0.0) or 0.0),
                                size=int(r.get("size", 0) or 0),
                                venue=None,
                                source=str(r.get("source", "alpaca:unknown")),
                                ingest_ts=(r["ingest_ts"].to_pydatetime() if pd.notna(r["ingest_ts"]) else None),
                            )
                        )
                    except Exception:
                        continue
                if len(mts) >= 20:
                    out.f99_ms = freshness_p99_ms(mts)
                    out.offs_ms = clock_offset_median_ms(mts)

    bars_ok = (out.bars_age_s is not None and out.bars_age_s <= 60.0 and (out.bars_cov_1m or 0.0) >= cov_threshold)
    trades_ok = (out.trades_age_s is not None and out.trades_age_s <= 10.0 and out.trades_1m >= 20)
    out.healthy = bool(bars_ok or trades_ok)
    return out

@dataclass
class QueueProbe:
    by_status: Dict[str, int]
    depth: int
    dead: int

def probe_queue(db_path: Path) -> QueueProbe:
    by = {"queued": 0, "processing": 0, "done": 0, "dead": 0}
    depth = dead = 0
    if not db_path.exists():
        return QueueProbe(by, depth, dead)
    try:
        con = sqlite3.connect(str(db_path))
        cur = con.cursor()
        for status, cnt in cur.execute("SELECT status, COUNT(*) FROM queue GROUP BY status").fetchall():
            by[str(status)] = int(cnt)
        depth = by.get("queued", 0) + by.get("processing", 0)
        dead = by.get("dead", 0)
        con.close()
    except Exception:
        pass
    return QueueProbe(by, depth, dead)

@dataclass
class LLMProbe:
    proposals_15m: int
    applied_15m: int
    accept_rate: Optional[float]
    freeze: Optional[bool]
    threshold_bps: Optional[float]
    cost_day: Optional[float]

def probe_llm(llm_dir: Path, params_dir: Path, symbol: str) -> LLMProbe:
    now = now_utc()
    day = _latest_day_dir(llm_dir)
    props = applied = 0
    rate = None
    freeze = None
    threshold = None
    cost = None

    # proposals/applied
    if day:
        props_p = day / f"proposals_{symbol}.parquet"
        ap_p = day / f"applied_{symbol}.parquet"
        dfp = _read_parquet_safe(props_p)
        if dfp is not None and not dfp.empty and "ts" in dfp.columns:
            dfp["ts"] = _safe_dt_series(dfp["ts"])
            props = int(dfp[dfp["ts"] >= (now - pd.Timedelta(minutes=15))].shape[0])
            if "cost_usd" in dfp.columns:
                cost = float(dfp["cost_usd"].sum())
        dfa = _read_parquet_safe(ap_p)
        if dfa is not None and not dfa.empty and "ts" in dfa.columns:
            dfa["ts"] = _safe_dt_series(dfa["ts"])
            a15 = dfa[(dfa["ts"] >= (now - pd.Timedelta(minutes=15))) & (dfa.get("delta_bps", 0).abs() > 0)]
            applied = int(a15.shape[0])
            rate = (applied / props) if props else 0.0
            if "freeze" in dfa.columns and not dfa.empty:
                freeze = bool(dfa.tail(1)["freeze"].iloc[0])

    # controller state (authoritative freeze flag if present)
    st_p = Path("data/ops/controller_state.json")
    if st_p.exists():
        try:
            st = json.loads(st_p.read_text())
            freeze = bool(st.get("freeze", freeze))
        except Exception:
            pass

    # runtime threshold
    rp = params_dir / f"runtime_{symbol}.json"
    if rp.exists():
        try:
            threshold = float(json.loads(rp.read_text()).get("signal_threshold_bps", 0.5))
        except Exception:
            threshold = 0.5
    else:
        threshold = 0.5

    return LLMProbe(props, applied, rate, freeze, threshold, cost)

@dataclass
class UptimeProbe:
    uptime_pct: int
    per_service: Dict[str, Tuple[bool, Optional[float]]]

def probe_uptime(hb_dir: Path) -> UptimeProbe:
    services = ["feedd", "advisor", "controller", "engined", "execd"]
    now = now_utc()
    ok = 0
    per: Dict[str, Tuple[bool, Optional[float]]] = {}
    for s in services:
        f = hb_dir / f"{s}.json"
        alive = False; age = None
        if f.exists():
            try:
                ts = _safe_dt_series(pd.Series([json.loads(f.read_text()).get("ts")])).iloc[0]
                age = float((now - ts).total_seconds())
                alive = age <= 75.0
            except Exception:
                alive = False
        per[s] = (alive, age)
        ok += int(alive)
    pct = int(100 * ok / max(1, len(services)))
    return UptimeProbe(pct, per)

# ---------- CLI

@app.command()
def main(
    symbol: str = typer.Option("SPY"),
    live_dir: str = typer.Option("data/live"),
    llm_dir: str = typer.Option("data/llm"),
    exec_dir: str = typer.Option("data/exec"),
    params_dir: str = typer.Option("data/params"),
    queue_path: str = typer.Option("data/queue.db"),
    window_min: int = typer.Option(1, help="Window for coverage/trade stats"),
    coverage_threshold: float = typer.Option(0.50),
    watch: int = typer.Option(0, help="Refresh every N seconds; 0=one-shot"),
    verbose: bool = typer.Option(False),
):
    live_root = Path(live_dir)
    llm_root = Path(llm_dir)
    exec_root = Path(exec_dir)
    params_root = Path(params_dir)
    queue_p = Path(queue_path)

    def render_once():
        feed = probe_feed(live_root, symbol, window_min, coverage_threshold)
        q = probe_queue(queue_p)
        llm = probe_llm(llm_root, params_root, symbol)
        up = probe_uptime(Path("data/ops/heartbeat"))

        # One-line summary
        line = (
            f"OPS | feed={'PASS' if feed.healthy else 'FAIL'} "
            f"| cov { _format_pct(feed.bars_cov_1m) } "
            f"| bar_age { _format_s(feed.bars_age_s) } "
            f"| trades_age { _format_s(feed.trades_age_s) } "
            f"| trades_{window_min}m {feed.trades_1m} "
            f"| fresh_p99 { _format_ms(feed.f99_ms) } "
            f"| queue q:{q.by_status.get('queued',0)} proc:{q.by_status.get('processing',0)} dead:{q.dead} "
            f"| freeze {llm.freeze if llm.freeze is not None else 'NA'} "
            f"| th { (f'{llm.threshold_bps:.3f}bps' if llm.threshold_bps is not None else 'NA') } "
            f"| llm {llm.proposals_15m}→{llm.applied_15m} ({_format_pct(llm.accept_rate)}) "
            f"| uptime {up.uptime_pct}%"
        )
        typer.echo(line)

        if verbose:
            day = _latest_day_dir(live_root)
            typer.echo("\n--- DETAIL ---")
            typer.echo(f"day={day.name if day else 'NA'}  symbol={symbol}")
            typer.echo(f"Bars: rows={feed.bars_rows} age={_format_s(feed.bars_age_s)} cov_1m={_format_pct(feed.bars_cov_1m)}")
            typer.echo(f"Trades: rows={feed.trades_rows} age={_format_s(feed.trades_age_s)} "
                       f"last_{window_min}m={feed.trades_1m} ingest_ts%={_format_pct(feed.ingest_ratio)} "
                       f"fresh_p99={_format_ms(feed.f99_ms)} clock_offset={_format_ms(feed.offs_ms)}")
            typer.echo(f"Queue: {q.by_status} depth={q.depth} dead={q.dead}")
            typer.echo(f"LLM: proposals_15m={llm.proposals_15m} applied_15m={llm.applied_15m} "
                       f"accept_rate={_format_pct(llm.accept_rate)} freeze={llm.freeze} "
                       f"threshold_bps={(f'{llm.threshold_bps:.3f}' if llm.threshold_bps is not None else 'NA')} "
                       f"cost_day={(f'${llm.cost_day:.2f}' if llm.cost_day is not None else 'NA')}")
            for svc, (alive, age) in up.per_service.items():
                typer.echo(f"HB: {svc:9s} alive={alive} age={_format_s(age)}")

    if watch and watch > 0:
        try:
            while True:
                render_once()
                time.sleep(watch)
        except KeyboardInterrupt:
            return
    else:
        render_once()

if __name__ == "__main__":
    app()
