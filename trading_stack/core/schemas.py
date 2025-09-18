from __future__ import annotations
from typing import Optional, Literal, List
from pydantic import BaseModel, Field
from datetime import datetime

class MarketTrade(BaseModel):
    ts: datetime = Field(..., description="Exchange timestamp (UTC)")
    symbol: str
    price: float
    size: int
    venue: Optional[str] = None
    source: Optional[str] = None

class MarketQuote(BaseModel):
    ts: datetime
    symbol: str
    bid: float
    ask: float
    bid_size: int
    ask_size: int
    source: Optional[str] = None

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
    limit: Optional[float] = None
    tag: Optional[str] = None
    ts: datetime

class OrderState(BaseModel):
    broker_order_id: Optional[str] = None
    state: Literal["NEW","ACK","REJ","PARTIAL","FILL","CANCEL"]
    reason: Optional[str] = None
    ts: datetime

class Fill(BaseModel):
    ts: datetime
    symbol: str
    side: Literal["BUY","SELL"]
    qty: float
    price: float
    fee: float = 0.0
    order_tag: Optional[str] = None

class LedgerEntry(BaseModel):
    ts: datetime
    kind: Literal["INTENT","ACK","FILL","CANCEL","REJ","PNL_SNAPSHOT"]
    data: dict

class LLMParamProposal(BaseModel):
    ts: datetime
    symbol: str
    params: dict
    notes: Optional[str] = None
