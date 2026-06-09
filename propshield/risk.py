"""Risk management and position sizing.

Sizing is driven by a percentage of account equity. Given a risk level
(low/medium/high), the stop-loss is placed an ATR multiple away from entry,
and the position quantity is chosen so that hitting the stop loses exactly the
configured fraction of equity.
"""

from __future__ import annotations

from propshield.config import RiskConfig
from propshield.models import AccountState, Side, Signal, TradePlan


class RiskManager:
    """Turns a Signal + account state into a fully-sized TradePlan."""

    def __init__(self, config: RiskConfig):
        self.config = config

    def levels(self) -> list[str]:
        return list(self.config.presets.keys())

    def build_plan(
        self,
        signal: Signal,
        account: AccountState,
        level: str,
    ) -> TradePlan:
        """Construct a sized trade plan, or raise ValueError if not viable."""
        risk_pct = min(self.config.risk_pct(level), self.config.max_risk_pct)
        equity = account.equity
        if equity <= 0:
            raise ValueError("Account equity is zero or negative; cannot size trade.")

        risk_amount = equity * risk_pct

        entry = signal.price
        stop_distance = self.config.atr_stop_mult * signal.atr
        if stop_distance <= 0:
            raise ValueError("Stop distance is zero; cannot size trade.")

        # Quantity such that (stop_distance * qty) == risk_amount.
        quantity = risk_amount / stop_distance
        quantity = self._round_quantity(quantity)
        if quantity <= 0:
            raise ValueError(
                "Computed position size rounds to zero — risk too small for this "
                "instrument's volatility."
            )

        tp_distance = stop_distance * self.config.reward_risk_ratio
        if signal.side is Side.BUY:
            stop_loss = entry - stop_distance
            take_profit = entry + tp_distance
        else:
            stop_loss = entry + stop_distance
            take_profit = entry - tp_distance

        # Actual risk after rounding the quantity.
        actual_risk = stop_distance * quantity

        return TradePlan(
            signal=signal,
            quantity=quantity,
            entry_price=round(entry, 5),
            stop_loss=round(stop_loss, 5),
            take_profit=round(take_profit, 5),
            risk_amount=round(actual_risk, 2),
            risk_pct=risk_pct,
        )

    @staticmethod
    def _round_quantity(qty: float) -> float:
        """Round to a sensible lot increment.

        Index CFDs typically trade in 0.01 increments. We round down to avoid
        ever risking more than intended.
        """
        import math

        rounded = math.floor(qty * 100) / 100.0
        return max(0.0, rounded)

    def can_open(self, account: AccountState) -> bool:
        """Whether another position may be opened under the position cap."""
        return account.open_positions < self.config.max_open_positions
