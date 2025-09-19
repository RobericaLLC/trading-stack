from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

try:
    from ib_insync import IB, LimitOrder, MarketOrder, Stock, Trade
except ImportError:  # pragma: no cover
    IB = None  # type: ignore[assignment,misc,unused-ignore]

from trading_stack.core.schemas import NewOrder


@dataclass
class PlaceResult:
    trade: Trade
    ack_ts: datetime


class IBKRAdapter:
    def __init__(self, host: str = "127.0.0.1", port: int = 7497, client_id: int = 7) -> None:
        if IB is None:
            raise RuntimeError("ib_insync not installed. Install extra: pip install '.[ib]'")
        self.ib = IB()
        self.host, self.port, self.client_id = host, port, client_id

    def connect(self) -> None:
        self.ib.connect(self.host, self.port, clientId=self.client_id)

    def disconnect(self) -> None:
        self.ib.disconnect()

    def place(self, order: NewOrder) -> PlaceResult:
        c = Stock(order.symbol, "SMART", "USD")
        o: MarketOrder | LimitOrder
        if order.limit is None:
            o = MarketOrder(order.side, int(order.qty))
        else:
            o = LimitOrder(order.side, int(order.qty), order.limit)
        t: Trade = self.ib.placeOrder(c, o)

        # Wait specifically for first transition to PreSubmitted/Submitted.
        ack_ts: datetime | None = None
        for _ in range(80):  # up to ~8s
            self.ib.waitOnUpdate(timeout=0.1)
            status = (t.orderStatus.status or "").lower()
            if status in ("presubmitted", "submitted"):
                ack_ts = datetime.now(UTC)
                break

        if ack_ts is None:
            # Fallback: still return, but the scorecard will show it.
            ack_ts = datetime.now(UTC)

        return PlaceResult(trade=t, ack_ts=ack_ts)

    def cancel(self, trade: Trade) -> None:
        self.ib.cancelOrder(trade.order)
        self.ib.waitOnUpdate(timeout=5.0)
