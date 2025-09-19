from datetime import UTC, datetime

from trading_stack.execution.state_machine import ExecState


def test_state_machine_happy_path() -> None:
    ts0 = datetime(2025, 1, 1, tzinfo=UTC)
    s = ExecState(tag="t1", symbol="SPY", side="BUY", qty=2, remaining=2, created_ts=ts0)
    s.on_ack(ts0)
    s.on_partial(ts0, 500.0, 1)
    assert s.state == "PARTIAL"
    assert s.remaining == 1
    s.on_fill(ts0, 500.2, 1)
    assert s.state == "FILL"
    assert s.remaining == 0
