import numpy as np
import pandas as pd

from propshield.config import StrategyConfig
from propshield.models import Instrument, Side
from propshield.strategy.scout import ScoutStrategy


def _ohlc_from_close(close: np.ndarray) -> pd.DataFrame:
    close = np.asarray(close, dtype="float64")
    wig = np.abs(np.diff(close, prepend=close[0])) + 1.0
    return pd.DataFrame(
        {
            "open": np.concatenate([[close[0]], close[:-1]]),
            "high": close + wig,
            "low": close - wig,
            "close": close,
            "volume": np.full(len(close), 1000.0),
        }
    )


def test_uptrend_gives_buy():
    close = np.linspace(1000, 1400, 300)
    df = _ohlc_from_close(close)
    sig = ScoutStrategy(StrategyConfig()).evaluate(
        Instrument(1, "TEST"), df
    )
    assert sig is not None
    assert sig.side is Side.BUY
    assert sig.score > 0


def test_downtrend_gives_sell():
    close = np.linspace(1400, 1000, 300)
    df = _ohlc_from_close(close)
    sig = ScoutStrategy(StrategyConfig()).evaluate(
        Instrument(1, "TEST"), df
    )
    assert sig is not None
    assert sig.side is Side.SELL


def test_insufficient_history_returns_none():
    df = _ohlc_from_close(np.linspace(1000, 1100, 50))
    sig = ScoutStrategy(StrategyConfig()).evaluate(Instrument(1, "TEST"), df)
    assert sig is None


def test_score_within_bounds():
    rng = np.random.default_rng(7)
    close = np.cumsum(rng.normal(scale=2, size=400)) + 5000
    df = _ohlc_from_close(close)
    sig = ScoutStrategy(StrategyConfig()).evaluate(Instrument(1, "TEST"), df)
    assert sig is not None
    assert 0.0 <= sig.score <= 100.0
    assert sig.atr > 0
