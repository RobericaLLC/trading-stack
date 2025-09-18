from datetime import UTC, datetime, timedelta

from trading_stack.core.schemas import MarketTrade
from trading_stack.ingest.aggregators import aggregate_trades_to_1s_bars


def test_aggregate_trades_to_1s_bars() -> None:
    t0 = datetime(2024, 9, 10, 14, 30, 0, tzinfo=UTC)
    trades = [
        MarketTrade(ts=t0, symbol="SPY", price=500.0, size=10),
        MarketTrade(ts=t0 + timedelta(milliseconds=400), symbol="SPY", price=500.1, size=5),
        MarketTrade(
            ts=t0 + timedelta(seconds=1, milliseconds=10), symbol="SPY", price=499.9, size=7
        ),
    ]
    bars = aggregate_trades_to_1s_bars(trades, "SPY")
    assert len(bars) == 2
    assert bars[0].open == 500.0
    assert bars[0].close == 500.1
    assert bars[0].volume == 15
    assert bars[1].close == 499.9
