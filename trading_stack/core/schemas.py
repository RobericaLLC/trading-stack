from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MarketTrade(BaseModel):
    ts: datetime = Field(..., description="Exchange timestamp (UTC)")
    symbol: str
    price: float
    size: int
    venue: str | None = None
    source: str | None = None
    ingest_ts: datetime | None = None

class MarketQuote(BaseModel):
    ts: datetime
    symbol: str
    bid: float
    ask: float
    bid_size: int
    ask_size: int
    source: str | None = None

class Bar1s(BaseModel):
    ts: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int

class NewOrder(BaseModel):
    symbol: str
    side: Literal["BUY","SELL"]
    qty: float
    tif: Literal["IOC","DAY","GTC"] = "DAY"
    limit: float | None = None
    tag: str | None = None
    ts: datetime

class OrderState(BaseModel):
    broker_order_id: str | None = None
    state: Literal["NEW","ACK","REJ","PARTIAL","FILL","CANCEL"]
    reason: str | None = None
    ts: datetime

class Fill(BaseModel):
    ts: datetime
    symbol: str
    side: Literal["BUY","SELL"]
    qty: float
    price: float
    fee: float = 0.0
    order_tag: str | None = None

class LedgerEntry(BaseModel):
    ts: datetime
    kind: Literal["INTENT","ACK","FILL","CANCEL","REJ","PNL_SNAPSHOT"]
    data: dict

class LLMParamProposal(BaseModel):
    ts: datetime
    symbol: str
    params: dict
    notes: str | None = None
