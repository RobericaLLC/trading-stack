from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json


def touch_heartbeat(name: str, root: str = "data/ops/heartbeat") -> None:
    """Touch a heartbeat file for the given service name."""
    p = Path(root)
    p.mkdir(parents=True, exist_ok=True)
    f = p / f"{name}.json"
    f.write_text(json.dumps({"ts": datetime.now(timezone.utc).isoformat()}))


def touch_heartbeat_legacy(name: str, root: str = "RUN/heartbeat") -> None:
    """Touch a legacy heartbeat file for compatibility with existing scorecard."""
    p = Path(root)
    p.mkdir(parents=True, exist_ok=True)
    f = p / f"{name}.hb"
    # Just touch the file to update mtime
    f.touch()


def beat(service: str, root: str = "data/ops/heartbeat") -> None:
    """Simplified heartbeat writer."""
    p = Path(root); p.mkdir(parents=True, exist_ok=True)
    (p / f"{service}.json").write_text(
        json.dumps({"ts": datetime.now(timezone.utc).isoformat()}),
        encoding="utf-8"
    )
