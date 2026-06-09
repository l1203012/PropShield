import numpy as np
import pandas as pd

from propshield import indicators as ind


def _series(values):
    return pd.Series(values, dtype="float64")


def test_ema_tracks_constant():
    s = _series([10.0] * 50)
    assert abs(ind.ema(s, 10).iloc[-1] - 10.0) < 1e-9


def test_rsi_all_up_is_100():
    s = _series(list(range(1, 60)))
    assert ind.rsi(s, 14).iloc[-1] == 100.0


def test_rsi_all_down_is_low():
    s = _series(list(range(60, 1, -1)))
    assert ind.rsi(s, 14).iloc[-1] < 1.0


def test_rsi_bounds():
    rng = np.random.default_rng(0)
    s = _series(np.cumsum(rng.normal(size=200)) + 100)
    r = ind.rsi(s, 14).dropna()
    assert (r >= 0).all() and (r <= 100).all()


def test_atr_positive():
    rng = np.random.default_rng(1)
    close = np.cumsum(rng.normal(size=200)) + 1000
    df = pd.DataFrame(
        {
            "high": close + np.abs(rng.normal(size=200)),
            "low": close - np.abs(rng.normal(size=200)),
            "close": close,
        }
    )
    atr = ind.atr(df, 14).dropna()
    assert (atr > 0).all()


def test_macd_columns():
    s = _series(np.linspace(100, 200, 100))
    out = ind.macd(s)
    assert set(out.columns) == {"macd", "signal", "hist"}
    # Steady uptrend -> positive MACD line near the end.
    assert out["macd"].iloc[-1] > 0


def test_bollinger_pct_b_range():
    rng = np.random.default_rng(2)
    s = _series(np.cumsum(rng.normal(size=200)) + 100)
    bb = ind.bollinger(s, 20)
    assert {"mid", "upper", "lower", "pct_b"} <= set(bb.columns)
    valid = bb.dropna(subset=["upper", "lower"])
    assert (valid["upper"] >= valid["lower"]).all()
