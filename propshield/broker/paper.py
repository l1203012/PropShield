"""A fully offline paper-trading broker.

The paper broker synthesises realistic OHLCV data with a per-symbol random
walk (deterministic per seed), tracks a simulated account, and fills market
orders at the latest synthetic price. It lets the entire bot run, be tested,
and be demoed with zero credentials and no network access.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from propshield.broker.base import Broker
from propshield.models import AccountState, Instrument, Position, Quote, Side

# Representative index instruments with rough price levels and volatility.
_INDEX_PROFILE = {
    "US30": (38_500.0, 0.008),
    "NAS100": (17_800.0, 0.012),
    "SPX500": (5_100.0, 0.009),
    "GER40": (18_000.0, 0.010),
    "UK100": (7_900.0, 0.007),
    "JP225": (39_000.0, 0.011),
    "US2000": (2_050.0, 0.013),
    "FRA40": (8_050.0, 0.009),
}

_RESOLUTION_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1H": 60,
    "4H": 240,
    "1D": 1440,
}

_LOOKBACK_BARS = {
    "1D": 1,
    "5D": 5,
    "1W": 7,
    "2W": 14,
    "1M": 30,
    "3M": 90,
}


def _seed_for(symbol: str) -> int:
    digest = hashlib.sha256(symbol.encode()).hexdigest()
    return int(digest[:8], 16)


class PaperBroker(Broker):
    """Offline simulated broker."""

    name = "paper"

    def __init__(self, starting_balance: float = 100_000.0):
        self._balance = starting_balance
        self._equity = starting_balance
        self._positions: dict[str, Position] = {}
        self._next_id = 1
        self._instruments: list[Instrument] = [
            Instrument(instrument_id=i + 1, symbol=sym, name=f"{sym} Index")
            for i, sym in enumerate(_INDEX_PROFILE)
        ]
        self._connected = False

    # -- lifecycle -----------------------------------------------------------
    def connect(self) -> None:
        self._connected = True

    def get_account_state(self) -> AccountState:
        return AccountState(
            balance=round(self._balance, 2),
            equity=round(self._equity, 2),
            currency="USD",
            open_positions=len(self._positions),
        )

    def get_instruments(self) -> list[Instrument]:
        return list(self._instruments)

    # -- market data ---------------------------------------------------------
    def _profile(self, symbol: str) -> tuple[float, float]:
        return _INDEX_PROFILE.get(symbol, (10_000.0, 0.01))

    def get_price_history(
        self, instrument: Instrument, resolution: str, lookback_period: str
    ) -> pd.DataFrame:
        base_price, daily_vol = self._profile(instrument.symbol)
        minutes = _RESOLUTION_MINUTES.get(resolution, 60)
        days = _LOOKBACK_BARS.get(lookback_period, 30)
        n_bars = max(60, int(days * 1440 / minutes))
        n_bars = min(n_bars, 2000)  # keep it bounded

        rng = np.random.default_rng(_seed_for(instrument.symbol))
        # Per-bar volatility scaled from a daily figure.
        bar_vol = daily_vol * np.sqrt(minutes / 1440.0)
        # A mild persistent drift gives each index a discernible trend.
        drift = (rng.random() - 0.5) * bar_vol * 0.3

        returns = rng.normal(loc=drift, scale=bar_vol, size=n_bars)
        log_walk = np.cumsum(returns)
        # Anchor the walk so the most recent close is always ``base_price``,
        # independent of resolution/lookback. This keeps the "current price"
        # consistent between scans and quotes (a real broker behaves this way).
        log_walk = log_walk - log_walk[-1]
        close = base_price * np.exp(log_walk)
        open_ = np.concatenate([[close[0]], close[:-1]])
        # Intrabar range proportional to volatility.
        wick = np.abs(rng.normal(scale=bar_vol, size=n_bars)) * close
        high = np.maximum(open_, close) + wick
        low = np.minimum(open_, close) - wick
        volume = rng.integers(500, 5000, size=n_bars).astype(float)

        end = datetime.utcnow()
        index = pd.date_range(
            end=end, periods=n_bars, freq=timedelta(minutes=minutes)
        )
        return pd.DataFrame(
            {
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            },
            index=index,
        )

    def _last_price(self, instrument: Instrument) -> float:
        hist = self.get_price_history(instrument, "1H", "5D")
        return float(hist["close"].iloc[-1])

    def get_quote(self, instrument: Instrument) -> Quote:
        price = self._last_price(instrument)
        spread = price * 0.0001  # 1bp synthetic spread
        return Quote(
            symbol=instrument.symbol,
            bid=price - spread / 2,
            ask=price + spread / 2,
        )

    # -- trading -------------------------------------------------------------
    def place_order(
        self,
        instrument: Instrument,
        side: Side,
        quantity: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> str:
        quote = self.get_quote(instrument)
        fill = quote.ask if side is Side.BUY else quote.bid
        position_id = f"paper-{self._next_id}"
        self._next_id += 1
        self._positions[position_id] = Position(
            position_id=position_id,
            symbol=instrument.symbol,
            side=side,
            quantity=quantity,
            entry_price=fill,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        return position_id

    def get_positions(self) -> list[Position]:
        # Mark-to-market against the latest synthetic price.
        positions = []
        for pos in self._positions.values():
            instrument = self.resolve_instrument(pos.symbol)
            if instrument is not None:
                price = self._last_price(instrument)
                pos.unrealized_pnl = round(
                    (price - pos.entry_price) * pos.side.sign * pos.quantity, 2
                )
            positions.append(pos)
        return positions

    def close_position(self, position_id: str) -> None:
        pos = self._positions.pop(position_id, None)
        if pos is None:
            raise KeyError(f"Unknown position: {position_id}")
        instrument = self.resolve_instrument(pos.symbol)
        if instrument is not None:
            price = self._last_price(instrument)
            realized = (price - pos.entry_price) * pos.side.sign * pos.quantity
            self._balance += realized
            self._equity = self._balance
