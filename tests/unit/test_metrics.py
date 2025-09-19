from datetime import UTC, datetime, timedelta

from trading_stack.core.schemas import MarketTrade
from trading_stack.ingest.metrics import freshness_p99_ms, rth_gap_events


def _t(n: int) -> datetime:
    return datetime(2024, 9, 10, 14, 30, 0, tzinfo=UTC) + timedelta(seconds=n)


def test_freshness_and_gaps() -> None:
    trades = [
        MarketTrade(
            ts=_t(0), symbol="SPY", price=1.0, size=1, ingest_ts=_t(0) + timedelta(milliseconds=120)
        ),
        MarketTrade(
            ts=_t(1), symbol="SPY", price=1.0, size=1, ingest_ts=_t(1) + timedelta(milliseconds=80)
        ),
        MarketTrade(
            ts=_t(4), symbol="SPY", price=1.0, size=1, ingest_ts=_t(4) + timedelta(milliseconds=100)
        ),  # 3s gap (>2)
    ]
    f99 = freshness_p99_ms(trades)
    assert 80.0 <= f99 <= 200.0
    gaps = rth_gap_events(trades, max_gap_sec=2)
    assert gaps == 1
