from __future__ import annotations

from pathlib import Path

import pandas as pd


def main(path: str) -> None:
    p = Path(path)
    df = pd.read_parquet(p)
    total = len(df)
    has_ingest = df["ingest_ts"].notna().sum() if "ingest_ts" in df.columns else 0
    print(f"path={p} rows={total} ingest_ts_present={has_ingest} ({has_ingest/total:.0%})")
    if total:
        print(df[["ts", "ingest_ts"]].head(3))
        print(df[["ts", "ingest_ts"]].tail(3))

if __name__ == "__main__":
    import sys
    main(sys.argv[1])
