from __future__ import annotations

import time
from datetime import UTC, datetime


class TradingClock:
    """Monotonic trading clock keyed to feed timestamps or wall clock as fallback."""

    def __init__(self) -> None:
        self._last_feed_ts_ns: int | None = None
        self._mono0 = time.monotonic_ns()

    def tick_from_feed(self, ts: datetime) -> datetime:
        ns = int(ts.replace(tzinfo=UTC).timestamp() * 1e9)
        if self._last_feed_ts_ns is None or ns >= self._last_feed_ts_ns:
            self._last_feed_ts_ns = ns
        return datetime.fromtimestamp(self._last_feed_ts_ns / 1e9, tz=UTC)

    def now(self) -> datetime:
        # Fallback to wall clock (UTC)
        return datetime.now(UTC)
