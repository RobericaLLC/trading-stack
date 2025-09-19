from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

State = Literal["NEW", "ACK", "REJ", "PARTIAL", "FILL", "CANCEL"]

@dataclass
class ExecState:
    tag: str
    symbol: str
    side: Literal["BUY", "SELL"]
    qty: float
    remaining: float
    state: State = "NEW"
    created_ts: datetime = field(default_factory=lambda: datetime.now(UTC))
    ack_ts: datetime | None = None
    fill_qty: float = 0.0
    avg_fill_px: float = 0.0
    rej_reason: str | None = None
    cancel_ts: datetime | None = None

    def on_ack(self, ts: datetime) -> None:
        if self.state in ("NEW",):
            self.state = "ACK"
            self.ack_ts = ts

    def on_rej(self, ts: datetime, reason: str) -> None:  # noqa: ARG002
        if self.state in ("NEW", "ACK"):
            self.state = "REJ"
            self.rej_reason = reason

    def on_partial(self, ts: datetime, px: float, qty: float) -> None:  # noqa: ARG002
        if self.state in ("ACK", "PARTIAL"):
            self.state = "PARTIAL"
            self.fill_qty += qty
            self.remaining = max(0.0, self.qty - self.fill_qty)
            # rolling VWAP
            self.avg_fill_px = (
                (self.avg_fill_px * (self.fill_qty - qty)) + px * qty
            ) / max(self.fill_qty, 1e-9)
            if self.remaining == 0:
                self.state = "FILL"

    def on_fill(self, ts: datetime, px: float, qty: float) -> None:
        self.on_partial(ts, px, qty)  # escalates to FILL if remaining==0

    def on_cancel(self, ts: datetime) -> None:
        if self.state in ("NEW", "ACK", "PARTIAL"):
            self.state = "CANCEL"
            self.cancel_ts = ts
