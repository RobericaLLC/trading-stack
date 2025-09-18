from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TypeVar

import pandas as pd
from pydantic import BaseModel

T = TypeVar('T', bound=BaseModel)


def _df_from_models(items: Iterable[BaseModel]) -> pd.DataFrame:
    rows = [i.model_dump() for i in items]
    return pd.DataFrame(rows)

def write_events(path: str | Path, items: Iterable[BaseModel]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = _df_from_models(items)
    if df.empty:
        return
    df.to_parquet(path, index=False)

def read_events(path: str | Path, model: type[T]) -> list[T]:
    df = pd.read_parquet(path)
    out = []
    for _, row in df.iterrows():
        d = row.to_dict()
        out.append(model.model_validate(d))
    return out
