"""Assembly helpers: build a configured TradingEngine and broker.

Keeping construction in one place means the terminal, tests, and any future
entry points all wire the bot up identically.
"""

from __future__ import annotations

from propshield.broker.base import Broker
from propshield.broker.paper import PaperBroker
from propshield.config import Config
from propshield.engine import TradingEngine
from propshield.risk import RiskManager
from propshield.strategy.scout import ScoutStrategy


def build_broker(config: Config, paper: bool) -> Broker:
    """Create the appropriate broker.

    ``paper=True`` always returns the offline simulator. Otherwise a
    TradeLocker broker is created for the configured (demo/live) environment,
    which requires complete credentials.
    """
    if paper:
        return PaperBroker(starting_balance=config.paper_balance)

    if not config.credentials.complete:
        raise RuntimeError(
            "TradeLocker credentials are incomplete. Set TRADELOCKER_USERNAME, "
            "TRADELOCKER_PASSWORD and TRADELOCKER_SERVER (e.g. in a .env file), "
            "or run in paper mode."
        )

    # Imported lazily so paper mode never needs the SDK.
    from propshield.broker.tradelocker_client import TradeLockerBroker

    return TradeLockerBroker(
        environment=config.environment_url,
        username=config.credentials.username,  # type: ignore[arg-type]
        password=config.credentials.password,  # type: ignore[arg-type]
        server=config.credentials.server,  # type: ignore[arg-type]
    )


def build_engine(config: Config, paper: bool) -> TradingEngine:
    """Build a fully-wired engine with the scout strategy and risk manager."""
    broker = build_broker(config, paper)
    broker.connect()
    strategy = ScoutStrategy(config.strategy)
    risk = RiskManager(config.risk)
    return TradingEngine(config=config, broker=broker, strategy=strategy, risk=risk)
