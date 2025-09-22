from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import websockets
else:
    try:
        import websockets
    except Exception:  # pragma: no cover
        websockets = None

from trading_stack.core.schemas import MarketTrade

BASE = "wss://stream.data.alpaca.markets"

def _iso_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)

async def _ws_connect(feed_path: str) -> Any:
    if websockets is None:
        raise RuntimeError("websockets not installed. `pip install websockets`")
    uri = f"{BASE}/{feed_path}"
    return await websockets.connect(uri, ping_interval=15, ping_timeout=10)

async def stream_trades(symbol: str, feed: str = "v2/iex") -> AsyncIterator[MarketTrade]:
    """Async generator yielding MarketTrade indefinitely (until cancelled)."""
    key = os.environ.get("ALPACA_API_KEY_ID")
    secret = os.environ.get("ALPACA_API_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError("Set ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY in environment")

    while True:  # auto-reconnect loop
        try:
            async with await _ws_connect(feed) as ws:
                await ws.send(json.dumps({"action": "auth", "key": key, "secret": secret}))
                await ws.send(json.dumps({"action": "subscribe", "trades": [symbol]}))
                async for raw in ws:
                    now = datetime.now(UTC)
                    payload = json.loads(raw)
                    events = payload if isinstance(payload, list) else [payload]
                    for ev in events:
                        if ev.get("T") == "t":  # trade
                            ts = _iso_to_dt(ev["t"])
                            yield MarketTrade(
                                ts=ts,
                                symbol=str(ev["S"]),
                                price=float(ev["p"]),
                                size=int(ev["s"]),
                                venue=None,
                                source=f"alpaca:{feed}",
                                ingest_ts=now,
                            )
        except Exception:
            # brief backoff before reconnect
            await asyncio.sleep(1.0)

def capture_trades(symbol: str, minutes: int, feed: str = "v2/iex") -> list[MarketTrade]:
    """Finite capture variant (legacy)."""
    async def _run() -> list[MarketTrade]:
        out: list[MarketTrade] = []
        end_at = datetime.now(UTC).timestamp() + minutes * 60
        async for t in stream_trades(symbol, feed):
            out.append(t)
            if datetime.now(UTC).timestamp() >= end_at:
                break
        return out
    return asyncio.run(_run())