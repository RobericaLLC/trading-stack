from __future__ import annotations
from collections import deque
from trading_stack.core.schemas import Bar1s, NewOrder
from datetime import datetime, timezone

class MeanReversion1S:
    """
    Toy baseline: if close deviates > threshold from rolling mean, fade it.
    For scaffold purposes only; sizing is 1 unit.
    """
    def __init__(self, threshold: float = 0.5, window: int = 30, symbol: str = "SPY"):
        self.th = threshold
        self.window = window
        self.symbol = symbol
        self.buf: deque[float] = deque(maxlen=window)

    def on_bar(self, bar: Bar1s) -> list[NewOrder]:
        assert bar.symbol == self.symbol
        self.buf.append(bar.close)
        if len(self.buf) < self.window:
            return []
        mean = sum(self.buf) / len(self.buf)
        dev_bps = (bar.close / mean - 1.0) * 1e4
        orders: list[NewOrder] = []
        ts = bar.ts if bar.ts.tzinfo else bar.ts.replace(tzinfo=timezone.utc)
        if dev_bps > self.th:
            orders.append(NewOrder(symbol=self.symbol, side="SELL", qty=1, limit=bar.close, tag="mr_short", ts=ts))
        elif dev_bps < -self.th:
            orders.append(NewOrder(symbol=self.symbol, side="BUY", qty=1, limit=bar.close, tag="mr_long", ts=ts))
        return orders
