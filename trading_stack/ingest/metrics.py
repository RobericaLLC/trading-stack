from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, time
from zoneinfo import ZoneInfo

import numpy as np

from trading_stack.core.schemas import MarketTrade


def freshness_p99_ms(trades: Iterable[MarketTrade]) -> float:
    vals = []
    for t in trades:
        if t.ingest_ts is None:
            continue
        ts = t.ts if t.ts.tzinfo else t.ts.replace(tzinfo=UTC)
        ing = t.ingest_ts if t.ingest_ts.tzinfo else t.ingest_ts.replace(tzinfo=UTC)
        ms = (ing - ts).total_seconds() * 1_000.0
        if ms >= 0:
            vals.append(ms)
    if not vals:
        return float("inf")
    return float(np.percentile(vals, 99))

def rth_gap_events(
    trades: Iterable[MarketTrade], max_gap_sec: int = 2, tz_name: str = "America/New_York"
) -> int:
    tz = ZoneInfo(tz_name)
    filt = []
    for t in trades:
        ts = t.ts if t.ts.tzinfo else t.ts.replace(tzinfo=UTC)
        et = ts.astimezone(tz)
        if et.weekday() >= 5:
            continue
        if et.time() < time(9, 30) or et.time() >= time(16, 0):
            continue
        filt.append(ts)
    filt.sort()
    gaps = 0
    for i in range(1, len(filt)):
        if (filt[i] - filt[i - 1]).total_seconds() > max_gap_sec:
            gaps += 1
    return gaps
