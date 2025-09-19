from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TCA:
    arrival: float
    fills_wavg: float
    side: str  # "BUY" | "SELL"

    @property
    def shortfall_bps(self) -> float:
        if self.arrival <= 0:
            return 0.0
        if self.side == "BUY":
            return (self.fills_wavg / self.arrival - 1.0) * 1e4
        else:  # SELL -> cost if we sell below arrival
            return (1.0 - self.fills_wavg / self.arrival) * 1e4