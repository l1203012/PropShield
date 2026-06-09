"""Core data models shared across the bot.

These are plain dataclasses so they are trivial to construct, log, and test
without pulling in broker-specific types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Side(str, Enum):
    """Order/position direction."""

    BUY = "buy"
    SELL = "sell"

    @property
    def opposite(self) -> "Side":
        return Side.SELL if self is Side.BUY else Side.BUY

    @property
    def sign(self) -> int:
        """+1 for long, -1 for short. Useful for P&L math."""
        return 1 if self is Side.BUY else -1


@dataclass(frozen=True)
class Instrument:
    """A tradable instrument (e.g. an index CFD)."""

    instrument_id: int
    symbol: str
    name: str = ""

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.symbol


@dataclass(frozen=True)
class Quote:
    """A single point-in-time price snapshot."""

    symbol: str
    bid: float
    ask: float
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass
class AccountState:
    """Snapshot of the trading account."""

    balance: float
    equity: float
    currency: str = "USD"
    open_positions: int = 0


@dataclass
class Position:
    """An open position."""

    position_id: str
    symbol: str
    side: Side
    quantity: float
    entry_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    unrealized_pnl: float = 0.0


@dataclass
class Signal:
    """A trade idea produced by a strategy after scouting an instrument."""

    symbol: str
    side: Side
    score: float  # 0..100 composite conviction score
    price: float  # reference price used for the decision
    atr: float  # current ATR, used for stop placement
    reasons: list[str] = field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.symbol} {self.side.value.upper()} score={self.score:.1f}"


@dataclass
class TradePlan:
    """A fully-sized, ready-to-execute trade derived from a Signal."""

    signal: Signal
    quantity: float
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_amount: float  # account currency risked if stop is hit
    risk_pct: float  # fraction of equity risked

    @property
    def symbol(self) -> str:
        return self.signal.symbol

    @property
    def side(self) -> Side:
        return self.signal.side
