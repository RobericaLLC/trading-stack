"""Basic tests for trading_stack schemas."""
from datetime import UTC, datetime

import pytest

from trading_stack.core.schemas import Bar1s, MarketQuote, MarketTrade, NewOrder


def test_bar1s_creation() -> None:
    """Test creating a Bar1s instance."""
    ts = datetime.now(UTC)
    bar = Bar1s(
        ts=ts,
        symbol="SPY",
        open=500.0,
        high=501.0,
        low=499.0,
        close=500.5,
        volume=100
    )
    assert bar.symbol == "SPY"
    assert bar.open == 500.0
    assert bar.high == 501.0
    assert bar.low == 499.0
    assert bar.close == 500.5
    assert bar.volume == 100
    assert bar.ts == ts


def test_market_trade_creation() -> None:
    """Test creating a MarketTrade instance."""
    ts = datetime.now(UTC)
    trade = MarketTrade(
        ts=ts,
        symbol="SPY",
        price=500.0,
        size=100,
        venue="NYSE"
    )
    assert trade.symbol == "SPY"
    assert trade.price == 500.0
    assert trade.size == 100
    assert trade.venue == "NYSE"


def test_market_quote_creation() -> None:
    """Test creating a MarketQuote instance."""
    ts = datetime.now(UTC)
    quote = MarketQuote(
        ts=ts,
        symbol="SPY",
        bid=499.9,
        ask=500.1,
        bid_size=100,
        ask_size=200
    )
    assert quote.symbol == "SPY"
    assert quote.bid == 499.9
    assert quote.ask == 500.1
    assert quote.bid_size == 100
    assert quote.ask_size == 200


def test_new_order_creation() -> None:
    """Test creating a NewOrder instance."""
    ts = datetime.now(UTC)
    order = NewOrder(
        symbol="SPY",
        side="BUY",
        qty=10.0,
        tif="DAY",
        limit=500.0,
        tag="test_order",
        ts=ts
    )
    assert order.symbol == "SPY"
    assert order.side == "BUY"
    assert order.qty == 10.0
    assert order.tif == "DAY"
    assert order.limit == 500.0
    assert order.tag == "test_order"
