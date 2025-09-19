from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path

import typer

from trading_stack.adapters.ibkr.adapter import IBKRAdapter
from trading_stack.core.schemas import Bar1s, NewOrder
from trading_stack.execution.state_machine import ExecState
from trading_stack.storage.ledger import append_ledger
from trading_stack.storage.parquet_store import read_events
from trading_stack.tca.metrics import TCA

app = typer.Typer(help="execd: IBKR paper adapter CLI (one-shot & sanity)")


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TIF(str, Enum):
    IOC = "IOC"
    DAY = "DAY"
    GTC = "GTC"


def _env(k: str, default: str | None = None) -> str:
    v = os.environ.get(k, default)
    if v is None:
        raise RuntimeError(f"Set env {k}")
    return v


def _now() -> datetime:
    return datetime.now(UTC)


@app.command("ib-handshake")
def ib_handshake() -> None:
    host = _env("IB_GATEWAY_HOST", "127.0.0.1")
    port = int(_env("IB_GATEWAY_PORT", "7497"))
    cid = int(_env("IB_CLIENT_ID", "7"))
    ib = IBKRAdapter(host, port, cid)
    ib.connect()
    # round-trip: server time via .ib.reqCurrentTime() is available,
    # but we avoid deep ib_insync usage here.
    ib.disconnect()
    typer.echo("IBKR handshake OK")


def _arrival_from_bars(bars_path: str | None, ts: datetime, symbol: str) -> float | None:
    if not bars_path:
        return None
    p = Path(bars_path)
    if not p.exists():
        return None
    bars = read_events(p, Bar1s)
    # choose the last bar with ts <= intent ts
    prior = [b for b in bars if b.symbol == symbol and b.ts <= ts]
    if not prior:
        return None
    return prior[-1].close


@app.command("one-shot")
def one_shot(  # noqa: B008
    symbol: str = typer.Option("SPY"),
    side: Side = typer.Option(Side.BUY),  # noqa: B008
    qty: float = typer.Option(1),
    limit: float | None = typer.Option(None),
    tif: TIF = typer.Option(TIF.DAY),  # noqa: B008
    tag: str | None = typer.Option(None),
    bars_path: str | None = typer.Option(
        None, help="Path to bars1s_{symbol}.parquet for arrival px"
    ),
    ttl_sec: int = typer.Option(3, help="Auto-cancel after N seconds if not fully filled"),
    out_dir: str = typer.Option("data/exec", help="Ledger root"),
) -> None:
    # Intent
    ts = _now()
    tag = tag or f"oneshot_{symbol}_{int(ts.timestamp())}"
    order = NewOrder(
        symbol=symbol, side=side.value, qty=qty, limit=limit, tif=tif.value, tag=tag, ts=ts
    )
    arrival = _arrival_from_bars(bars_path, ts, symbol)
    ledger_day = Path(out_dir) / ts.date().isoformat()
    ledger_path = ledger_day / "ledger.parquet"
    append_ledger(
        ledger_path,
        [
            {
                "ts": ts,
                "kind": "INTENT",
                "tag": tag,
                "symbol": symbol,
                "side": side.value,
                "qty": qty,
                "limit": limit,
                "tif": tif.value,
                "arrival": arrival,
            }
        ],
    )

    # Place
    host = _env("IB_GATEWAY_HOST", "127.0.0.1")
    port = int(_env("IB_GATEWAY_PORT", "7497"))
    cid = int(_env("IB_CLIENT_ID", "7"))
    ib = IBKRAdapter(host, port, cid)
    ib.connect()
    state = ExecState(
        tag=tag, symbol=symbol, side=side.value, qty=qty, remaining=qty, created_ts=ts
    )
    res = ib.place(order)
    state.on_ack(res.ack_ts)
    append_ledger(ledger_path, [{"ts": ts, "event_ts": res.ack_ts, "kind": "ACK", "tag": tag}])

    # Wait for fills briefly, then cancel if needed
    prev_n = 0
    end_by = _now() + timedelta(seconds=ttl_sec)
    trade = res.trade

    while _now() < end_by:
        # drain updates
        trade.contract  # nudge ib_insync  # noqa: B018
        ib.ib.waitOnUpdate(timeout=0.25)

        fills = list(trade.fills or [])
        if len(fills) > prev_n:
            newfills = fills[prev_n:]
            for f in newfills:
                q = float(getattr(f.execution, "shares", 0) or 0)
                px = float(getattr(f.execution, "price", 0.0) or getattr(f, "price", 0.0) or 0.0)
                if q > 0 and px > 0:
                    state.on_partial(_now(), px, q)
                    append_ledger(
                        ledger_path,
                        [
                            {
                                "ts": ts,
                                "event_ts": _now(),
                                "kind": "FILL",
                                "tag": tag,
                                "fill_qty": q,
                                "avg_px": state.avg_fill_px,
                                "symbol": symbol,
                                "side": side.value,
                            }
                        ],
                    )
            prev_n = len(fills)

        if trade.isDone():
            break

    # If not fully filled by TTL, cancel
    if state.state != "FILL" and not trade.isDone():
        ib.cancel(trade)
        ib.ib.waitOnUpdate(timeout=2.0)
        state.on_cancel(_now())
        append_ledger(ledger_path, [{"ts": ts, "event_ts": _now(), "kind": "CANCEL", "tag": tag}])

    ib.disconnect()

    # TCA (if arrival present and filled)
    if state.fill_qty > 0 and arrival:
        tca = TCA(arrival=arrival, fills_wavg=state.avg_fill_px, side=side.value)
        append_ledger(
            ledger_path,
            [
                {
                    "ts": ts,
                    "event_ts": _now(),
                    "kind": "PNL_SNAPSHOT",
                    "tag": tag,
                    "shortfall_bps": tca.shortfall_bps,
                }
            ],
        )

    typer.echo(
        f"[one-shot] tag={tag} state={state.state} fill_qty={state.fill_qty} "
        f"avg_px={state.avg_fill_px or '—'} arrival={arrival or '—'}"
    )


@app.command("sanity-cancel")
def sanity_cancel(
    symbol: str = "SPY",
    side: Side = Side.BUY,
    qty: float = 1,
    limit: float = 0.01,  # ridiculous to avoid fills
    out_dir: str = "data/exec",
) -> None:
    """Place a far-off limit and immediately cancel; validates ACK+Cancel path."""
    ts = _now()
    tag = f"sanity_{symbol}_{int(ts.timestamp())}"
    order = NewOrder(
        symbol=symbol, side=side.value, qty=qty, limit=limit, tif="DAY", tag=tag, ts=ts
    )
    ledger_day = Path(out_dir) / ts.date().isoformat()
    ledger_path = ledger_day / "ledger.parquet"
    append_ledger(
        ledger_path,
        [
            {
                "ts": ts,
                "kind": "INTENT",
                "tag": tag,
                "symbol": symbol,
                "side": side.value,
                "qty": qty,
                "limit": limit,
            }
        ],
    )
    host = _env("IB_GATEWAY_HOST", "127.0.0.1")
    port = int(_env("IB_GATEWAY_PORT", "7497"))
    cid = int(_env("IB_CLIENT_ID", "7"))
    ib = IBKRAdapter(host, port, cid)
    ib.connect()
    res = ib.place(order)
    append_ledger(ledger_path, [{"ts": ts, "event_ts": res.ack_ts, "kind": "ACK", "tag": tag}])
    # immediate cancel
    ib.cancel(res.trade)
    append_ledger(ledger_path, [{"ts": ts, "event_ts": _now(), "kind": "CANCEL", "tag": tag}])
    ib.disconnect()
    typer.echo(f"[sanity-cancel] tag={tag} ACK+Cancel recorded")


if __name__ == "__main__":
    app()
