"""Strategy interface.

A strategy looks at a single instrument's price history and optionally
produces a :class:`~propshield.models.Signal`. The scout layer runs the
strategy across the whole watchlist and ranks the results.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd

from propshield.models import Instrument, Signal


class Strategy(ABC):
    """Base class for all strategies."""

    name: str = "strategy"

    @abstractmethod
    def evaluate(
        self, instrument: Instrument, history: pd.DataFrame
    ) -> Optional[Signal]:
        """Evaluate one instrument and return a Signal, or None if no setup.

        ``history`` is an OHLCV DataFrame (columns: open, high, low, close,
        volume) ordered oldest-to-newest.
        """
