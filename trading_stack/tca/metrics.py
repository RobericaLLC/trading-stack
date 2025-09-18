from __future__ import annotations
from dataclasses import dataclass

@dataclass
class TCA:
    arrival: float
    fills_wavg: float

    @property
    def shortfall_bps(self) -> float:
        if self.arrival <= 0:
            return 0.0
        return (self.fills_wavg / self.arrival - 1.0) * 1e4
