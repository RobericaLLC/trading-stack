"""Tests for storage functionality."""
from datetime import UTC, datetime, timedelta
from pathlib import Path

from trading_stack.core.schemas import Bar1s
from trading_stack.storage.parquet_store import read_events, write_events


def test_storage_round_trip(tmp_path: Path) -> None:
    """Test writing and reading events from parquet storage."""
    # Create sample bars
    now = datetime.now(UTC).replace(microsecond=0)
    bars = [
        Bar1s(
            ts=now,
            symbol="SPY",
            open=500.0,
            high=501.0,
            low=499.0,
            close=500.5,
            volume=100
        ),
        Bar1s(
            ts=now + timedelta(seconds=1),
            symbol="SPY",
            open=500.5,
            high=501.5,
            low=500.0,
            close=501.0,
            volume=150
        )
    ]
    
    # Write to temporary file
    test_file = tmp_path / "test_bars.parquet"
    write_events(test_file, bars)
    
    # Read back
    loaded_bars = read_events(test_file, Bar1s)
    
    # Verify
    assert len(loaded_bars) == 2
    assert loaded_bars[0].symbol == "SPY"
    assert loaded_bars[0].close == 500.5
    assert loaded_bars[1].close == 501.0
    
    # Verify timestamps are preserved
    assert loaded_bars[0].ts == bars[0].ts
    assert loaded_bars[1].ts == bars[1].ts


def test_empty_storage(tmp_path: Path) -> None:
    """Test writing empty list of events."""
    test_file = tmp_path / "empty.parquet"
    write_events(test_file, [])
    
    # File should not be created for empty data
    assert not test_file.exists()
