"""Technical indicators implemented in pure pandas/numpy.

Avoiding TA-Lib keeps installation friction-free (no C extensions). Each
function takes a pandas Series/DataFrame and returns a Series aligned to the
input index.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(window=period, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder's smoothing)."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    # When avg_loss is 0 the asset only went up -> RSI 100.
    out = out.where(avg_loss != 0.0, 100.0)
    return out


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range. Expects columns: high, low, close."""
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)
    true_range = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    """MACD line, signal line, and histogram."""
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "hist": hist})


def bollinger(
    series: pd.Series, period: int = 20, num_std: float = 2.0
) -> pd.DataFrame:
    """Bollinger Bands: middle (SMA), upper, lower, and %B position."""
    mid = sma(series, period)
    std = series.rolling(window=period, min_periods=period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    width = (upper - lower)
    pct_b = (series - lower) / width.replace(0.0, np.nan)
    return pd.DataFrame(
        {"mid": mid, "upper": upper, "lower": lower, "pct_b": pct_b}
    )


def rolling_high(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).max()


def rolling_low(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).min()
