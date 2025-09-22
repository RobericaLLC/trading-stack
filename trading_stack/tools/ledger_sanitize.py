from __future__ import annotations

from pathlib import Path

import pandas as pd
import typer

app = typer.Typer(help="Validate and repair basic ledger invariants")

NEEDED = {
    "INTENT": ["ts","tag","symbol","side","qty"],
    "ACK":    ["ts","event_ts","tag"],
    "FILL":   ["ts","event_ts","tag","fill_qty","avg_px"],  # symbol/side will be backfilled
    "CANCEL": ["ts","event_ts","tag"],
    "REJ":    ["ts","tag","reason"],
}

def _to_utc(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], utc=True, errors="coerce")
    return df

@app.command()
def main(ledger_path: str) -> None:
    p = Path(ledger_path)
    if not p.exists():
        typer.echo(f"missing {p}")
        raise typer.Exit(1)
    df = pd.read_parquet(p)
    if df.empty:
        typer.echo("empty ledger")
        raise typer.Exit(1)

    # enforce ts/event_ts UTC
    df = _to_utc(df, ["ts","event_ts"])

    # backfill symbol/side on FILL from INTENT via tag
    intents = df[df["kind"]=="INTENT"][["tag","symbol","side"]].drop_duplicates()
    if "symbol" not in df.columns:
        df["symbol"] = pd.NA
    if "side" not in df.columns:
        df["side"] = pd.NA
    fills = df["kind"]=="FILL"
    # Create a mapping of tag -> (symbol, side) from intents
    tag_map = intents.set_index("tag")[["symbol","side"]].to_dict("index")
    # Apply the mapping to fills
    for idx in df[fills].index:
        tag = df.loc[idx, "tag"]
        if tag in tag_map:
            if pd.isna(df.loc[idx, "symbol"]):
                df.loc[idx, "symbol"] = tag_map[tag]["symbol"]
            if pd.isna(df.loc[idx, "side"]):
                df.loc[idx, "side"] = tag_map[tag]["side"]

    # drop obvious corrupt rows (missing required columns per kind)
    keep = []
    for _idx, r in df.iterrows():
        k = r["kind"]
        need = NEEDED.get(k, [])
        ok = all(c in df.columns and pd.notna(r.get(c)) for c in need)
        keep.append(ok)
    df = df[keep]

    # dedupe (by (kind, tag, event_ts or ts))
    if "event_ts" in df.columns:
        df["dedup_key"] = (
            df["kind"].astype(str) + "|" + 
            df["tag"].astype(str) + "|" + 
            df["event_ts"].astype(str)
        )
    else:
        df["dedup_key"] = (
            df["kind"].astype(str) + "|" + 
            df["tag"].astype(str) + "|" + 
            df["ts"].astype(str)
        )
    df = df.drop_duplicates(subset=["dedup_key"]).drop(columns=["dedup_key"])

    # write sanitized copy next to original
    out = p.with_name(p.stem + "_sanitized.parquet")
    df.to_parquet(out, index=False)
    typer.echo(f"sanitized -> {out} (rows={len(df)})")

if __name__ == "__main__":
    app()
