from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import typer

from trading_stack.adapters.alpaca.feed import capture_trades, stream_trades
from trading_stack.core.schemas import Bar1s, MarketTrade
from trading_stack.core.schemas import MarketTrade as MT
from trading_stack.ingest.aggregators import aggregate_trades_to_1s_bars
from trading_stack.ingest.metrics import clock_offset_median_ms, freshness_p99_ms

app = typer.Typer(help="feedd: data ingest (synthetic + live adapters + verification)")

# ---------- utilities

def _utcnow() -> datetime:
    return datetime.now(UTC)

def _now_pd_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")

def _day_dir(out_root: Path, ts: datetime) -> Path:
    d = out_root / ts.date().isoformat()
    d.mkdir(parents=True, exist_ok=True)
    return d

def _append_parquet(path: Path, df_new: pd.DataFrame) -> None:
    if df_new is None or df_new.empty:
        return
    if path.exists():
        df = pd.read_parquet(path)
        df = pd.concat([df, df_new], ignore_index=True)
    else:
        df = df_new
    df.to_parquet(path, index=False)

# ---------- synthetic for smoke

@app.command("synthetic")
def synthetic(
    symbol: str = "SPY",
    minutes: int = 1,
    out: str = "data/synth_bars.parquet",
):
    now = _utcnow().replace(microsecond=0)
    bars: list[Bar1s] = []
    px = 500.0
    for i in range(minutes * 60):
        ts = now + timedelta(seconds=i)
        drift = random.gauss(0, 0.02)
        px = max(1.0, px + drift)
        high = px + abs(random.gauss(0, 0.05))
        low = px - abs(random.gauss(0, 0.05))
        vol = max(1, int(abs(random.gauss(50, 20))))
        bars.append(Bar1s(ts=ts, symbol=symbol, open=px, high=high, low=low, close=px, volume=vol))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([b.model_dump(mode="json") for b in bars]).to_parquet(out, index=False)
    typer.echo(f"Wrote {len(bars)} synthetic bars to {out}")

# ---------- live alpaca (finite and continuous)

@dataclass
class _BarBucket:
    o: float
    h: float
    low: float
    c: float
    v: int

@app.command("live-alpaca")
def live_alpaca(
    symbol: str = typer.Option("SPY", help="Ticker (US equities)"),
    minutes: int = typer.Option(5, help="Capture duration; 0 = run forever"),
    feed: str = typer.Option("v2/iex", help="v2/iex, v2/sip, or v2/test"),
    out_dir: str = typer.Option("data/live", help="Root dir for captures"),
    flush_sec: float = typer.Option(5.0, help="Flush interval in seconds"),
):
    """
    Capture live trades via Alpaca WS.
    - minutes > 0: finite capture, write once.
    - minutes == 0: continuous; flush trades & 1s bars every `flush_sec`.
    """
    out_root = Path(out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    if minutes > 0:
        trades = capture_trades(symbol=symbol, minutes=minutes, feed=feed)
        bars = aggregate_trades_to_1s_bars(trades, symbol=symbol)
        day = (trades[0].ts if trades else _utcnow()).date().isoformat()
        root = out_root / day
        root.mkdir(parents=True, exist_ok=True)
        trades_path = root / f"trades_{symbol}.parquet"
        bars_path = root / f"bars1s_{symbol}.parquet"
        _append_parquet(trades_path, pd.DataFrame([t.model_dump(mode="json") for t in trades]))
        _append_parquet(bars_path, pd.DataFrame([b.model_dump(mode="json") for b in bars]))
        typer.echo(f"[live-alpaca] trades={len(trades)} bars={len(bars)} → {root}")
        raise typer.Exit(0)

    # minutes == 0 → continuous
    async def run():
        last_written_sec: datetime | None = None
        buckets: dict[datetime, _BarBucket] = {}
        trades_buf: list[MarketTrade] = []
        next_flush = _utcnow() + timedelta(seconds=flush_sec)
        async for t in stream_trades(symbol, feed=feed):
            trades_buf.append(t)
            sec = t.ts.replace(microsecond=0, tzinfo=UTC)
            b = buckets.get(sec)
            px = float(t.price)
            if b is None:
                buckets[sec] = _BarBucket(o=px, h=px, low=px, c=px, v=int(t.size))
            else:
                b.h = max(b.h, px)
                b.low = min(b.low, px)
                b.c = px
                b.v += int(t.size)

            now = _utcnow()
            if now >= next_flush:
                root = _day_dir(out_root, now)
                trades_path = root / f"trades_{symbol}.parquet"
                bars_path = root / f"bars1s_{symbol}.parquet"

                if trades_buf:
                    df_tr = pd.DataFrame([x.model_dump(mode="json") for x in trades_buf])
                    _append_parquet(trades_path, df_tr)
                    trades_buf.clear()

                new_bars: list[Bar1s] = []
                for k in sorted(buckets.keys()):
                    if last_written_sec is None or k > last_written_sec:
                        bb = buckets[k]
                        new_bars.append(Bar1s(
                            ts=k, symbol=symbol, open=bb.o, high=bb.h, 
                            low=bb.low, close=bb.c, volume=bb.v
                        ))
                if new_bars:
                    df_bars = pd.DataFrame([b.model_dump(mode="json") for b in new_bars])
                    _append_parquet(bars_path, df_bars)
                    last_written_sec = new_bars[-1].ts

                next_flush = now + timedelta(seconds=flush_sec)

    asyncio.run(run())

# ---------- verify live artifacts (health read)

@app.command("verify")
def verify(
    symbol: str = typer.Option("SPY", help="Ticker"),
    out_dir: str = typer.Option("data/live", help="Root dir for live captures"),
    window_min: int = typer.Option(1, help="Window (minutes) for coverage/trade stats"),
    coverage_threshold: float = typer.Option(0.50, help="Bars per-second coverage threshold"),
):
    """
    Quick health check for latest live day:
      - Bars: last ts age, 1s coverage in last window, rows
      - Trades: last ingest age, trades in window, %% with ingest_ts,
        freshness p99, clock offset median
      Health PASS if (bars fresh & coverage>=threshold) OR 
        (trades fresh with >=20 last minute).
    """
    root = Path(out_dir)
    day_dirs = sorted([p for p in root.glob("*") if p.is_dir()])
    if not day_dirs:
        typer.echo(f"[verify] No day directories under {out_dir}")
        raise typer.Exit(code=1)
    day = day_dirs[-1]
    now = _now_pd_utc()

    bars_path = day / f"bars1s_{symbol}.parquet"
    trades_path = day / f"trades_{symbol}.parquet"

    # ---- Bars diagnostics
    bars_rows = 0
    bars_last_ts = None
    bars_age_s = None
    bars_cov = 0.0
    bars_ok = False
    if bars_path.exists():
        dfb = pd.read_parquet(bars_path)
        bars_rows = len(dfb)
        if bars_rows > 0 and "ts" in dfb.columns:
            dfb["ts"] = pd.to_datetime(dfb["ts"], utc=True)
            dfb = dfb.sort_values("ts")
            bars_last_ts = dfb["ts"].iloc[-1]
            bars_age_s = float((now - bars_last_ts).total_seconds())
            cut = now - pd.Timedelta(minutes=window_min)
            window = dfb[dfb["ts"] >= cut]
            secs = window["ts"].dt.floor("s").nunique()
            bars_cov = secs / float(60 * window_min)
            bars_ok = (bars_age_s <= 60.0) and (bars_cov >= coverage_threshold)

    # ---- Trades diagnostics
    trades_rows = 0
    trades_last_ing = None
    trades_last_age_s = None
    trades_last_min = 0
    ingest_ratio = 0.0
    f99 = None
    offs = None
    trades_ok = False
    if trades_path.exists():
        dft = pd.read_parquet(trades_path)
        trades_rows = len(dft)
        if trades_rows > 0:
            # determine timestamp columns
            if "ingest_ts" in dft.columns:
                dft["ingest_ts"] = pd.to_datetime(dft["ingest_ts"], utc=True, errors="coerce")
                ingest_ratio = float(dft["ingest_ts"].notna().sum()) / trades_rows
                tcol = "ingest_ts"
            else:
                tcol = "ts" if "ts" in dft.columns else None
            if "ts" in dft.columns:
                dft["ts"] = pd.to_datetime(dft["ts"], utc=True, errors="coerce")
            if tcol is not None and dft[tcol].notna().any():
                dft = dft.sort_values(tcol)
                trades_last_ing = dft[tcol].dropna().iloc[-1]
                trades_last_age_s = float((now - trades_last_ing).total_seconds())
                cut = now - pd.Timedelta(minutes=window_min)
                trades_last_min = int(dft[dft[tcol] >= cut].shape[0])
                # freshness / clock offset if we have enough with ingest_ts
                if "ingest_ts" in dft.columns and dft["ingest_ts"].notna().sum() >= 20:
                    # Build a small sample of MarketTrade for metrics
                    sample = dft[dft["ingest_ts"].notna()].tail(500)
                    trades_models: list[MT] = []
                    # only pick the fields we can map; missing price/size handled safely
                    for _, r in sample.iterrows():
                        try:
                            trades_models.append(
                                MT(
                                    ts=r["ts"].to_pydatetime() if pd.notna(r["ts"]) else _utcnow(),
                                    symbol=str(r.get("symbol", symbol)),
                                    price=float(r.get("price", 0.0) or 0.0),
                                    size=int(r.get("size", 0) or 0),
                                    venue=None,
                                    source=str(r.get("source", "alpaca:unknown")),
                                    ingest_ts=r["ingest_ts"].to_pydatetime(),
                                )
                            )
                        except Exception:
                            continue
                    if trades_models:
                        f99 = freshness_p99_ms(trades_models)
                        offs = clock_offset_median_ms(trades_models)
            # trades health relaxed vs bars; match controller logic
            trades_ok = (
                trades_last_age_s is not None and trades_last_age_s <= 10.0
            ) and (trades_last_min >= 20)

    # ---- Health decision
    healthy = bool(bars_ok or trades_ok)

    # ---- Print report
    def _fmt(v): return "NA" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))
    typer.echo(f"── FEED VERIFY (symbol={symbol}, day={day.name})")
    typer.echo(f"Bars path:   {bars_path}  (exists={bars_path.exists()})")
    typer.echo(
        f"  rows={bars_rows}  last_ts={bars_last_ts}  age_s={_fmt(bars_age_s)}  "
        f"coverage_{window_min}m={bars_cov:.0%}  PASS={bars_ok}"
    )
    typer.echo(f"Trades path: {trades_path}  (exists={trades_path.exists()})")
    typer.echo(
        f"  rows={trades_rows}  last_ingest_age_s={_fmt(trades_last_age_s)}  "
        f"trades_{window_min}m={trades_last_min}  ingest_ts%={ingest_ratio:.0%}  "
        f"PASS={trades_ok}"
    )
    if f99 is not None or offs is not None:
        typer.echo(f"  freshness_p99_ms={_fmt(f99)}  clock_offset_median_ms={_fmt(offs)}")
    typer.echo(
        f"HEALTH: {'PASS' if healthy else 'FAIL'}  "
        f"(bars_ok={bars_ok}, trades_ok={trades_ok})"
    )

    if not healthy:
        typer.echo("\nHints:")
        typer.echo(
            "  • Ensure feedd is running in continuous mode:  "
            "live-alpaca --minutes 0 --flush_sec 5"
        )
        typer.echo(
            "  • Market hours? IEX thins out off-hours. During RTH, "
            "coverage should exceed 50%."
        )
        typer.echo("  • Verify Windows time sync (w32tm) so ingest_ts is sane.")


if __name__ == "__main__":
    app()