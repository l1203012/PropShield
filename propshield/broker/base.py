"""Abstract broker interface.

Every concrete broker (TradeLocker, paper) implements this contract so the
strategy, risk, and execution layers never depend on a specific platform.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd

from propshield.models import AccountState, Instrument, Position, Quote, Side


class Broker(ABC):
    """Minimal interface the rest of the bot relies on."""

    name: str = "broker"

    @abstractmethod
    def connect(self) -> None:
        """Establish a session. Should be idempotent."""

    @abstractmethod
    def get_account_state(self) -> AccountState:
        """Return balance / equity / open-position count."""

    @abstractmethod
    def get_instruments(self) -> list[Instrument]:
        """Return all tradable instruments."""

    @abstractmethod
    def get_price_history(
        self, instrument: Instrument, resolution: str, lookback_period: str
    ) -> pd.DataFrame:
        """Return OHLCV history as a DataFrame.

        Index is a DatetimeIndex; columns are: open, high, low, close, volume.
        """

    @abstractmethod
    def get_quote(self, instrument: Instrument) -> Quote:
        """Return the latest bid/ask quote."""

    @abstractmethod
    def place_order(
        self,
        instrument: Instrument,
        side: Side,
        quantity: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> str:
        """Place a market order. Returns a broker order/position id."""

    @abstractmethod
    def get_positions(self) -> list[Position]:
        """Return currently open positions."""

    @abstractmethod
    def close_position(self, position_id: str) -> None:
        """Close an open position by id."""

    def resolve_instrument(self, symbol: str) -> Optional[Instrument]:
        """Find an instrument by (case-insensitive) symbol name.

        Tolerates minor naming differences by also matching when the requested
        symbol is a prefix of a broker symbol (e.g. ``US30`` -> ``US30.cash``).
        """
        symbol_norm = symbol.strip().lower()
        instruments = self.get_instruments()
        # Exact match first.
        for ins in instruments:
            if ins.symbol.lower() == symbol_norm:
                return ins
        # Then prefix / contains match.
        for ins in instruments:
            name = ins.symbol.lower()
            if name.startswith(symbol_norm) or symbol_norm in name:
                return ins
        return None
