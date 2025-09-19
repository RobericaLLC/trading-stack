from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProviderResponse:
    params: dict[str, float]
    notes: str
    cost_usd: float


class Provider:
    name: str = "base"

    def propose(self, features: dict[str, float]) -> ProviderResponse:  # pragma: no cover
        raise NotImplementedError


class RulesProvider(Provider):
    name = "rules"

    def propose(self, features: dict[str, float]) -> ProviderResponse:
        # Heuristics: raise threshold + cut risk when vol expands or spread widens
        vol = features.get("realized_vol_bps", 5.0)
        spr = features.get("spread_proxy_bps", 1.0)
        trend = features.get("trend_bps", 0.0)
        base_th = 0.5
        th = min(3.0, max(0.3, base_th + 0.03 * (vol - 5.0) + 0.02 * (spr - 1.0)))
        # If trend is strong (|trend|>5bps), be more conservative
        if abs(trend) > 5.0:
            th *= 1.2
        risk_mult = max(0.25, min(1.5, 1.0 - 0.03 * (vol - 5.0) - 0.02 * (spr - 1.0)))
        return ProviderResponse(
            params={"signal.threshold_bps": round(th, 3), "risk.multiplier": round(risk_mult, 3)},
            notes=f"vol={vol:.1f} spr={spr:.1f} trend={trend:.1f}",
            cost_usd=0.0,
        )


def get_provider(kind: str) -> Provider:
    # Later: "openai", "anthropic", "gemini" etc.
    if kind.lower() in ("rules", "default", "local"):
        return RulesProvider()
    raise ValueError(f"unknown provider: {kind}")
