from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from trading_stack.llm.advisor import append_proposal, make_proposal


def test_rules_provider_roundtrip(tmp_path: Path) -> None:
    # fabricate bars
    p = tmp_path / "bars.parquet"
    ts0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    rows = []
    px = 500.0
    for i in range(120):
        px += 0.01
        rows.append(
            {
                "ts": (ts0 + timedelta(seconds=i)).isoformat(),
                "symbol": "SPY",
                "open": px,
                "high": px + 0.05,
                "low": px - 0.05,
                "close": px,
                "volume": 10,
            }
        )
    pd.DataFrame(rows).to_parquet(p, index=False)
    prop = make_proposal("SPY", p, "rules")
    assert "signal.threshold_bps" in prop.params and "risk.multiplier" in prop.params
    out = tmp_path / "props.parquet"
    append_proposal(out, prop, provider="rules", cost_usd=0.0)
    df = pd.read_parquet(out)
    assert len(df) == 1
