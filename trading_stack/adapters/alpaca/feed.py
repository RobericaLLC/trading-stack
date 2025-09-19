from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta

try:
    import websockets
except ImportError:  # pragma: no cover
    websockets = None  # type: ignore[assignment,unused-ignore]

from trading_stack.core.schemas import MarketTrade

# Feed paths: v2/iex (free), v2/sip (paid), v2/test (always-on test) per docs.
# https://docs.alpaca.markets/docs/real-time-stock-pricing-data
BASE = "wss://stream.data.alpaca.markets"

def _iso_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)

async def _run_ws(
    symbol: str, minutes: int, feed_path: str, key: str, secret: str
) -> list[MarketTrade]:
    assert websockets is not None, "websockets not installed. `pip install websockets`"
    uri = f"{BASE}/{feed_path}"
    # If minutes == 0, run continuously
    end_at = None if minutes == 0 else datetime.now(UTC) + timedelta(minutes=minutes)
    trades: list[MarketTrade] = []
    async with websockets.connect(uri, ping_interval=15, ping_timeout=10) as ws:
        # Authenticate via message: {"action":"auth","key":"...","secret":"..."}
        # https://docs.alpaca.markets/docs/streaming-market-data
        await ws.send(json.dumps({"action": "auth", "key": key, "secret": secret}))
        # Subscribe to trades channel
        await ws.send(json.dumps({"action": "subscribe", "trades": [symbol]}))

        while end_at is None or datetime.now(UTC) < end_at:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=30.0)
            except TimeoutError:
                continue
            now = datetime.now(UTC)
            payload = json.loads(raw)
            # All messages arrive as arrays
            # Control messages T: "success" | "error" | "subscription"
            events = payload if isinstance(payload, list) else [payload]
            for ev in events:
                T = ev.get("T")
                if T == "t":  # trade event (see doc schema)
                    # Example keys: S symbol, p price, s size, t RFC3339 timestamp
                    ts = _iso_to_dt(ev["t"])
                    trades.append(
                        MarketTrade(
                            ts=ts,
                            symbol=str(ev["S"]),
                            price=float(ev["p"]),
                            size=int(ev["s"]),
                            venue=None,
                            source=f"alpaca:{feed_path}",
                            ingest_ts=now,
                        )
                    )
                # ignore quotes/bars/status/control in this adapter
    return trades

def capture_trades(symbol: str, minutes: int, feed: str = "v2/iex") -> list[MarketTrade]:
    key = os.environ.get("ALPACA_API_KEY_ID")
    secret = os.environ.get("ALPACA_API_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError("Set ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY in environment")
    return asyncio.run(
        _run_ws(symbol=symbol, minutes=minutes, feed_path=feed, key=key, secret=secret)
    )
