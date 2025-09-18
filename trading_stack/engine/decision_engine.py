from __future__ import annotations

from trading_stack.core.schemas import Bar1s, NewOrder
from trading_stack.risk.gate import RiskConfig, pretrade_check
from trading_stack.strategy.baseline import MeanReversion1S


class DecisionEngine:
    def __init__(self, symbol: str, threshold: float, max_notional: float, price_band_bps: int):
        self.strategy = MeanReversion1S(threshold=threshold, symbol=symbol)
        self.risk = RiskConfig(max_notional=max_notional, price_band_bps=price_band_bps)
        self.last_px: float | None = None

    def on_bar(self, bar: Bar1s) -> list[NewOrder]:
        self.last_px = bar.close
        intents = self.strategy.on_bar(bar)
        out: list[NewOrder] = []
        for o in intents:
            ok, reason = pretrade_check(o, self.last_px, self.risk)
            if ok:
                out.append(o)
        return out
