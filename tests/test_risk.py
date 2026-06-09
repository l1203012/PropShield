import pytest

from propshield.config import RiskConfig
from propshield.models import AccountState, Side, Signal
from propshield.risk import RiskManager


def _signal(side=Side.BUY, price=10000.0, atr=50.0):
    return Signal(symbol="US30", side=side, score=80.0, price=price, atr=atr)


def test_position_size_matches_risk_budget():
    rm = RiskManager(RiskConfig())
    acct = AccountState(balance=100_000, equity=100_000)
    plan = rm.build_plan(_signal(), acct, "medium")  # 1% -> $1000 risk
    # stop distance = 2 * ATR(50) = 100; qty ~ 1000/100 = 10
    assert plan.quantity == pytest.approx(10.0, abs=0.01)
    # Risk after rounding should not exceed the 1% budget.
    assert plan.risk_amount <= 1000.0 + 1e-6


def test_long_stop_below_entry_and_tp_above():
    rm = RiskManager(RiskConfig())
    acct = AccountState(balance=100_000, equity=100_000)
    plan = rm.build_plan(_signal(side=Side.BUY), acct, "low")
    assert plan.stop_loss < plan.entry_price < plan.take_profit


def test_short_stop_above_entry_and_tp_below():
    rm = RiskManager(RiskConfig())
    acct = AccountState(balance=100_000, equity=100_000)
    plan = rm.build_plan(_signal(side=Side.SELL), acct, "high")
    assert plan.take_profit < plan.entry_price < plan.stop_loss


def test_risk_levels_scale():
    rm = RiskManager(RiskConfig())
    acct = AccountState(balance=100_000, equity=100_000)
    low = rm.build_plan(_signal(), acct, "low")
    high = rm.build_plan(_signal(), acct, "high")
    assert high.quantity > low.quantity


def test_max_risk_pct_cap():
    cfg = RiskConfig(presets={"insane": 0.5}, default_level="insane", max_risk_pct=0.05)
    rm = RiskManager(cfg)
    acct = AccountState(balance=100_000, equity=100_000)
    plan = rm.build_plan(_signal(), acct, "insane")
    assert plan.risk_pct == 0.05


def test_zero_equity_raises():
    rm = RiskManager(RiskConfig())
    acct = AccountState(balance=0, equity=0)
    with pytest.raises(ValueError):
        rm.build_plan(_signal(), acct, "medium")


def test_can_open_respects_cap():
    rm = RiskManager(RiskConfig(max_open_positions=2))
    assert rm.can_open(AccountState(100_000, 100_000, open_positions=1))
    assert not rm.can_open(AccountState(100_000, 100_000, open_positions=2))
