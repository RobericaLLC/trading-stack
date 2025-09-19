from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from trading_stack.core.schemas import Bar1s, LLMParamProposal
from trading_stack.llm.router import ProviderResponse, get_provider


def _features_from_bars(bars: list[Bar1s]) -> dict[str, float]:
    import numpy as np

    if not bars:
        return {"realized_vol_bps": 0.0, "spread_proxy_bps": 0.0, "trend_bps": 0.0}
    closes = np.array([b.close for b in bars], dtype=float)
    rets = np.diff(closes) / closes[:-1]
    vol_bps = float(np.sqrt(np.mean(rets**2)) * 1e4) if len(rets) else 0.0
    # proxy for spread: normalized intrabar range
    ranges = np.array([max(0.0, b.high - b.low) / (b.close or 1.0) * 1e4 for b in bars])
    spr_bps = float(np.median(ranges)) if len(ranges) else 0.0
    trend_bps = float((closes[-1] / closes[0] - 1.0) * 1e4) if len(closes) > 1 else 0.0
    return {"realized_vol_bps": vol_bps, "spread_proxy_bps": spr_bps, "trend_bps": trend_bps}


def _bars_window(bars_path: Path, window_sec: int) -> list[Bar1s]:
    df = pd.read_parquet(bars_path)
    if df.empty:
        return []
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.sort_values("ts")
    cutoff = df["ts"].iloc[-1] - pd.Timedelta(seconds=window_sec)
    df = df[df["ts"] > cutoff]
    from trading_stack.core.schemas import Bar1s as Bar

    return [
        Bar.model_validate(r._asdict() if hasattr(r, "_asdict") else r.to_dict())
        for _, r in df.iterrows()
    ]


def make_proposal(symbol: str, bars_path: Path, provider_kind: str) -> LLMParamProposal:
    bars = _bars_window(bars_path, window_sec=120)  # last 2 minutes
    feats = _features_from_bars(bars)
    resp: ProviderResponse = get_provider(provider_kind).propose(feats)
    ts = datetime.now(UTC)
    proposal = LLMParamProposal(ts=ts, symbol=symbol, params=resp.params, notes=resp.notes)
    return proposal


def append_proposal(
    out_path: Path, proposal: LLMParamProposal, provider: str, cost_usd: float
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": proposal.ts.isoformat(),
        "symbol": proposal.symbol,
        "signal.threshold_bps": proposal.params.get("signal.threshold_bps"),
        "risk.multiplier": proposal.params.get("risk.multiplier"),
        "notes": proposal.notes or "",
        "provider": provider,
        "cost_usd": float(cost_usd),
    }
    # Append-row Parquet
    if out_path.exists():
        df = pd.read_parquet(out_path)
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        df = pd.DataFrame([row])
    df.to_parquet(out_path, index=False)
