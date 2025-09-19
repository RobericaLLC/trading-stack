from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from trading_stack.accounting.positions import compute_positions


def test_positions_from_incremental_avg(tmp_path: Path) -> None:
    p = tmp_path / "ledger.parquet"
    ts = datetime(2025,1,1,tzinfo=UTC)
    df = pd.DataFrame([
        {"kind":"FILL","tag":"t1","symbol":"SPY","side":"BUY","fill_qty":1,"avg_px":100.0,"event_ts":ts},
        {"kind":"FILL","tag":"t1","symbol":"SPY","side":"BUY","fill_qty":1,"avg_px":101.0,"event_ts":ts+timedelta(seconds=1)},
        {"kind":"FILL","tag":"t2","symbol":"SPY","side":"SELL","fill_qty":1,"avg_px":101.5,"event_ts":ts+timedelta(seconds=2)},
    ])
    df.to_parquet(p, index=False)
    snaps = compute_positions(p)
    s = snaps["SPY"]
    # After two buys (100, 102) avg 101; one sell at ~101.5 -> realized +0.5 on 1 share
    # Remaining 1 share @ 101
    assert abs(s.qty - 1.0) < 1e-9
    assert abs(s.avg_cost - 101.0) < 1e-6
    assert s.realized_pnl > 0.0
