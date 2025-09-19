from datetime import UTC, datetime
from pathlib import Path

from trading_stack.storage.ledger import append_ledger, read_ledger


def test_ledger_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "ledger.parquet"
    rows = [
        {
            "ts": datetime.now(UTC),
            "kind": "INTENT",
            "tag": "t1",
            "symbol": "SPY",
            "side": "BUY",
            "qty": 1,
            "limit": 500.0
        }
    ]
    append_ledger(p, rows)
    df = read_ledger(p)
    assert len(df) == 1
    assert df.iloc[0]["tag"] == "t1"
