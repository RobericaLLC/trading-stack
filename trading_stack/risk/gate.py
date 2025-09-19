from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from trading_stack.core.schemas import NewOrder


@dataclass
class RiskConfig:
    max_notional: float
    price_band_bps: int
    symbol_whitelist: set[str] = field(default_factory=lambda: {"SPY"})
    max_open_orders: int = 3
    daily_loss_stop_pct: float = 1.0  # 1% of equity
    killswitch_path: str = "RUN/HALT"


def price_band_ok(last: float, limit: float | None, band_bps: int) -> bool:
    if limit is None:
        return True
    band = last * band_bps / 10000.0
    return (limit >= last - band) and (limit <= last + band)


def is_killswitched(cfg: RiskConfig) -> bool:
    """Check if killswitch file exists."""
    return Path(cfg.killswitch_path).exists()


def pretrade_check(order: NewOrder, px_last: float, cfg: RiskConfig) -> tuple[bool, str]:
    """Run comprehensive pretrade risk checks."""
    # Check killswitch first
    if is_killswitched(cfg):
        return False, "killswitch active"

    # Symbol whitelist
    if order.symbol not in cfg.symbol_whitelist:
        return False, f"symbol {order.symbol} not in whitelist"

    # Max notional check
    notional = (order.limit or px_last) * order.qty
    if notional > cfg.max_notional:
        return False, f"notional {notional:.2f} > max {cfg.max_notional:.2f}"

    # Price band check
    if not price_band_ok(px_last, order.limit, cfg.price_band_bps):
        return False, "limit outside price band"

    # TODO: max_open_orders and daily_loss_stop require ledger state
    # These will be implemented when we have access to current positions

    return True, "OK"
