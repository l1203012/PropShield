"""Trading engine: scout the watchlist, rank setups, size and execute trades.

This is the orchestration layer that the terminal UI drives. It is broker- and
strategy-agnostic and never trades on its own — execution always goes through
:meth:`TradingEngine.execute`, which the caller invokes after any confirmation
gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from propshield.broker.base import Broker
from propshield.config import Config
from propshield.models import AccountState, Instrument, Signal, TradePlan
from propshield.risk import RiskManager
from propshield.strategy.base import Strategy


@dataclass
class ScanResult:
    """One instrument's scout outcome."""

    instrument: Instrument
    signal: Optional[Signal]
    error: Optional[str] = None


class TradingEngine:
    """Coordinates broker, strategy, and risk management."""

    def __init__(
        self,
        config: Config,
        broker: Broker,
        strategy: Strategy,
        risk: RiskManager,
    ):
        self.config = config
        self.broker = broker
        self.strategy = strategy
        self.risk = risk

    # -- discovery -----------------------------------------------------------
    def resolve_watchlist(self) -> list[Instrument]:
        """Map configured symbol names to the broker's actual instruments."""
        resolved: list[Instrument] = []
        seen: set[int] = set()
        for symbol in self.config.watchlist:
            instrument = self.broker.resolve_instrument(symbol)
            if instrument is not None and instrument.instrument_id not in seen:
                resolved.append(instrument)
                seen.add(instrument.instrument_id)
        return resolved

    # -- scouting ------------------------------------------------------------
    def scan(self, instruments: Optional[list[Instrument]] = None) -> list[ScanResult]:
        """Evaluate every watchlist instrument and return per-instrument results."""
        if instruments is None:
            instruments = self.resolve_watchlist()
        results: list[ScanResult] = []
        for instrument in instruments:
            try:
                history = self.broker.get_price_history(
                    instrument,
                    self.config.strategy.resolution,
                    self.config.strategy.lookback_period,
                )
                signal = self.strategy.evaluate(instrument, history)
                results.append(ScanResult(instrument=instrument, signal=signal))
            except Exception as exc:  # keep scanning other instruments
                results.append(
                    ScanResult(instrument=instrument, signal=None, error=str(exc))
                )
        return results

    def rank(self, results: list[ScanResult]) -> list[Signal]:
        """Return tradable signals sorted by descending conviction score."""
        signals = [r.signal for r in results if r.signal is not None]
        signals.sort(key=lambda s: s.score, reverse=True)
        return signals

    def best_signal(
        self, results: list[ScanResult], min_score: Optional[float] = None
    ) -> Optional[Signal]:
        """Highest-scoring signal that clears the minimum-score threshold."""
        threshold = (
            min_score if min_score is not None else self.config.strategy.min_score
        )
        ranked = self.rank(results)
        for signal in ranked:
            if signal.score >= threshold:
                return signal
        return None

    # -- sizing / execution --------------------------------------------------
    def account(self) -> AccountState:
        return self.broker.get_account_state()

    def plan(self, signal: Signal, level: str) -> TradePlan:
        return self.risk.build_plan(signal, self.account(), level)

    def execute(self, plan: TradePlan) -> str:
        """Place the order described by ``plan``. Returns the broker order id."""
        instrument = self.broker.resolve_instrument(plan.symbol)
        if instrument is None:
            raise ValueError(f"Instrument not found for symbol {plan.symbol}")
        if not self.risk.can_open(self.account()):
            raise RuntimeError(
                f"Position cap reached "
                f"({self.config.risk.max_open_positions} open)."
            )
        return self.broker.place_order(
            instrument=instrument,
            side=plan.side,
            quantity=plan.quantity,
            stop_loss=plan.stop_loss,
            take_profit=plan.take_profit,
        )
