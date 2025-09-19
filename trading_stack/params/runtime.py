from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class RuntimeParams:
    symbol: str
    signal_threshold_bps: float = 0.5
    risk_multiplier: float = 1.0
    updated_at: str = ""

    @staticmethod
    def load(path: Path, symbol: str) -> RuntimeParams:
        if not path.exists():
            rp = RuntimeParams(symbol=symbol, updated_at=datetime.now(UTC).isoformat())
            rp.save(path)
            return rp
        data = json.loads(path.read_text(encoding="utf-8"))
        return RuntimeParams(**data)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.updated_at = datetime.now(UTC).isoformat()
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def append_applied(out_parquet: Path, row: dict[str, Any]) -> None:
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    df_new = pd.DataFrame([row])
    if out_parquet.exists():
        df = pd.read_parquet(out_parquet)
        df = pd.concat([df, df_new], ignore_index=True)
    else:
        df = df_new
    df.to_parquet(out_parquet, index=False)
