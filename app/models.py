from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SignalDirection(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class Candle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class AIPrediction(BaseModel):
    label: str = "neutral"
    confidence: float = 0.0
    rationale: str = "AI prediction module placeholder; no model is used for live decisions."


class Signal(BaseModel):
    pair: str
    timeframe: str
    direction: SignalDirection
    entry: float
    rsi: float
    trend: str
    strategy: str
    confidence: float = Field(ge=0.0, le=1.0)
    stop_loss: float
    take_profit: float
    trailing_stop: float
    risk_reward: float
    risk_percent: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScannerState(BaseModel):
    running: bool = False
    last_scan_at: datetime | None = None
    last_error: str | None = None
    scanned_pairs: int = 0
    generated_signals: int = 0
