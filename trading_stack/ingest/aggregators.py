from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC

from trading_stack.core.schemas import Bar1s, MarketTrade


def aggregate_trades_to_1s_bars(trades: Iterable[MarketTrade], symbol: str) -> list[Bar1s]:
    """Deterministic 1s OHLCV from trades."""
    ts_sorted = sorted(
        (t for t in trades),
        key=lambda t: t.ts if t.ts.tzinfo else t.ts.replace(tzinfo=UTC),
    )
    buckets: dict[str, dict[str, float | int]] = {}
    for t in ts_sorted:
        ts = t.ts if t.ts.tzinfo else t.ts.replace(tzinfo=UTC)
        key = ts.replace(microsecond=0).isoformat()
        px = float(t.price)
        if key not in buckets:
            buckets[key] = {"open": px, "high": px, "low": px, "close": px, "volume": int(t.size)}
        else:
            b = buckets[key]
            b["high"] = max(b["high"], px)
            b["low"] = min(b["low"], px)
            b["close"] = px
            b["volume"] = int(b["volume"]) + int(t.size)
    bars: list[Bar1s] = []
    for key, v in sorted(buckets.items()):
        from datetime import datetime

        ts = datetime.fromisoformat(key.replace("Z", "+00:00"))
        bars.append(
            Bar1s(
                ts=ts,
                symbol=symbol,
                open=float(v["open"]),
                high=float(v["high"]),
                low=float(v["low"]),
                close=float(v["close"]),
                volume=int(v["volume"]),
            )
        )
    return bars
