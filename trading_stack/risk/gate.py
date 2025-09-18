from __future__ import annotations
from trading_stack.core.schemas import NewOrder
from dataclasses import dataclass

@dataclass
class RiskConfig:
    max_notional: float
    price_band_bps: int

def price_band_ok(last: float, limit: float | None, band_bps: int) -> bool:
    if limit is None:
        return True
    band = last * band_bps / 10000.0
    return (limit >= last - band) and (limit <= last + band)

def pretrade_check(order: NewOrder, px_last: float, cfg: RiskConfig) -> tuple[bool, str]:
    notional = (order.limit or px_last) * order.qty
    if notional > cfg.max_notional:
        return False, f"notional {notional:.2f} > max {cfg.max_notional:.2f}"
    if not price_band_ok(px_last, order.limit, cfg.price_band_bps):
        return False, "limit outside price band"
    return True, "OK"
