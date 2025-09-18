from __future__ import annotations

import argparse
import time

import pandas as pd

from trading_stack.core.schemas import MarketTrade


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True, help="Parquet events path")
    ap.add_argument("--speed", type=float, default=1.0, help="Replay speed multiplier")
    args = ap.parse_args()

    df = pd.read_parquet(args.path)
    if df.empty:
        print("No events.")
        return

    # Assume ts is UTC ISO or epoch ns convertible
    df['ts'] = pd.to_datetime(df['ts'], utc=True)

    t0 = df['ts'].iloc[0]
    wall0 = time.monotonic()
    for _, row in df.iterrows():
        ts = row['ts']
        # pacing
        delta = (ts - t0).total_seconds() / args.speed
        now = time.monotonic() - wall0
        if delta > now:
            time.sleep(delta - now)
        trade = MarketTrade.model_validate(row.to_dict())
        print(f"{trade.ts.isoformat()} {trade.symbol} {trade.size}@{trade.price}")

if __name__ == "__main__":
    main()
