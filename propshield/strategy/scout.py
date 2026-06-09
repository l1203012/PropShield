"""Multi-indicator scoring scout strategy.

For each instrument the scout computes a panel of indicators (trend, momentum,
volatility/breakout) and combines them into a single signed conviction score.
The sign decides direction (long/short); the magnitude (0..100) decides how
strong the setup is. The :class:`~propshield.engine.Scout` ranks instruments by
this score and the engine trades the strongest setups.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd

from propshield import indicators as ind
from propshield.config import StrategyConfig
from propshield.models import Instrument, Side, Signal


def _last(series: pd.Series) -> Optional[float]:
    """Last non-NaN value of a series, or None."""
    s = series.dropna()
    if s.empty:
        return None
    return float(s.iloc[-1])


def _clip(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


class ScoutStrategy:
    """Combines several indicators into one directional conviction score."""

    name = "multi-indicator-scout"

    # Relative weight of each component (normalised internally).
    WEIGHTS = {
        "trend": 0.25,  # EMA fast vs slow
        "long_trend": 0.20,  # price vs EMA(200)
        "macd": 0.20,  # MACD histogram
        "rsi": 0.15,  # momentum
        "breakout": 0.12,  # position in recent range
        "bollinger": 0.08,  # position within bands
    }

    def __init__(self, config: Optional[StrategyConfig] = None):
        self.config = config or StrategyConfig()

    def evaluate(
        self, instrument: Instrument, history: pd.DataFrame
    ) -> Optional[Signal]:
        cfg = self.config
        if history is None or len(history) < cfg.ema_trend:
            return None

        close = history["close"]
        price = _last(close)
        if price is None:
            return None

        ema_fast = _last(ind.ema(close, cfg.ema_fast))
        ema_slow = _last(ind.ema(close, cfg.ema_slow))
        ema_trend = _last(ind.ema(close, cfg.ema_trend))
        rsi_val = _last(ind.rsi(close, cfg.rsi_period))
        atr_val = _last(ind.atr(history, cfg.atr_period))
        macd_df = ind.macd(close)
        macd_hist = _last(macd_df["hist"])
        bb = ind.bollinger(close, cfg.bb_period)
        pct_b = _last(bb["pct_b"])
        high_n = _last(ind.rolling_high(history["high"], cfg.breakout_period))
        low_n = _last(ind.rolling_low(history["low"], cfg.breakout_period))

        # Any missing core input means we cannot trust the read.
        if None in (ema_fast, ema_slow, ema_trend, rsi_val, atr_val):
            return None
        if atr_val <= 0:
            return None

        votes: dict[str, float] = {}
        reasons: list[str] = []

        # 1. Short-term trend: EMA fast vs slow, scaled by separation.
        sep = (ema_fast - ema_slow) / ema_slow
        votes["trend"] = _clip(math.tanh(sep * 150))
        reasons.append(
            f"EMA{cfg.ema_fast}{'>' if ema_fast > ema_slow else '<'}EMA{cfg.ema_slow}"
        )

        # 2. Long-term trend: price vs EMA(200).
        long_sep = (price - ema_trend) / ema_trend
        votes["long_trend"] = _clip(math.tanh(long_sep * 60))
        reasons.append(
            f"price {'above' if price > ema_trend else 'below'} EMA{cfg.ema_trend}"
        )

        # 3. MACD histogram momentum (normalised by ATR for scale-invariance).
        if macd_hist is not None:
            votes["macd"] = _clip(math.tanh((macd_hist / atr_val) * 1.5))
            reasons.append(f"MACD hist {macd_hist:+.2f}")
        else:
            votes["macd"] = 0.0

        # 4. RSI momentum: distance from 50, dampened at extremes.
        rsi_vote = _clip((rsi_val - 50.0) / 50.0)
        if rsi_val > 75 or rsi_val < 25:
            rsi_vote *= 0.5  # avoid chasing overextended moves
        votes["rsi"] = rsi_vote
        reasons.append(f"RSI {rsi_val:.0f}")

        # 5. Breakout: position within the recent high/low range.
        if high_n is not None and low_n is not None and high_n > low_n:
            pos = (price - low_n) / (high_n - low_n)
            votes["breakout"] = _clip(2.0 * pos - 1.0)
        else:
            votes["breakout"] = 0.0

        # 6. Bollinger %B position.
        if pct_b is not None and not math.isnan(pct_b):
            votes["bollinger"] = _clip(2.0 * pct_b - 1.0)
        else:
            votes["bollinger"] = 0.0

        # Weighted net vote in [-1, 1].
        total_weight = sum(self.WEIGHTS.values())
        net = sum(self.WEIGHTS[k] * votes[k] for k in self.WEIGHTS) / total_weight

        side = Side.BUY if net >= 0 else Side.SELL
        score = abs(net) * 100.0

        # Penalise setups where the short- and long-term trends disagree with
        # the chosen direction: conviction should be coherent across horizons.
        if np.sign(votes["trend"]) != np.sign(net) and votes["trend"] != 0:
            score *= 0.85
        if np.sign(votes["long_trend"]) != np.sign(net) and votes["long_trend"] != 0:
            score *= 0.85

        direction_reasons = [r for r in reasons]
        return Signal(
            symbol=instrument.symbol,
            side=side,
            score=round(score, 2),
            price=price,
            atr=atr_val,
            reasons=direction_reasons,
        )
