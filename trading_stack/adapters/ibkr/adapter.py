from __future__ import annotations

from datetime import UTC, datetime

try:
    from ib_insync import IB, LimitOrder, MarketOrder, Stock
except ImportError:  # pragma: no cover
    IB = None

from trading_stack.core.schemas import NewOrder, OrderState


class IBKRAdapter:
    def __init__(self, host: str = "127.0.0.1", port: int = 7497, client_id: int = 7) -> None:
        if IB is None:
            raise RuntimeError("ib_insync not installed. Install extra: pip install '.[ib]'")
        self.ib = IB()
        self.host, self.port, self.client_id = host, port, client_id

    def connect(self) -> None:
        self.ib.connect(self.host, self.port, clientId=self.client_id)

    def place(self, order: NewOrder) -> OrderState:
        contract = Stock(order.symbol, "SMART", "USD")
        if order.limit is None:
            o = MarketOrder(order.side, int(order.qty))
        else:
            o = LimitOrder(order.side, int(order.qty), order.limit)
        t = self.ib.placeOrder(contract, o)
        state = OrderState(broker_order_id=str(t.order.orderId), state="NEW", ts=datetime.now(UTC))
        return state
