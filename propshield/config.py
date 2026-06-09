"""Configuration loading for PropShield.

Settings come from three layers (later overrides earlier):
  1. Built-in defaults (this module)
  2. A YAML config file (config/default.yaml)
  3. Environment variables / .env (credentials and environment selection)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

DEMO_URL = "https://demo.tradelocker.com"
LIVE_URL = "https://live.tradelocker.com"

# Default index watchlist. Symbol names vary slightly between brokers, so these
# are resolved against the broker's instrument list at runtime.
DEFAULT_WATCHLIST = [
    "US30",
    "NAS100",
    "SPX500",
    "GER40",
    "UK100",
    "JP225",
    "US2000",
    "FRA40",
]

# Risk presets: fraction of account equity risked per trade.
DEFAULT_RISK_PRESETS = {
    "low": 0.005,  # 0.5%
    "medium": 0.01,  # 1%
    "high": 0.02,  # 2%
}


@dataclass
class StrategyConfig:
    """Parameters for the multi-indicator scout strategy."""

    resolution: str = "1H"
    lookback_period: str = "1M"
    ema_fast: int = 21
    ema_slow: int = 50
    ema_trend: int = 200
    rsi_period: int = 14
    atr_period: int = 14
    breakout_period: int = 20
    bb_period: int = 20
    # Minimum composite score (0..100) required before a signal is tradable.
    min_score: float = 60.0


@dataclass
class RiskConfig:
    """Risk / position-sizing parameters."""

    presets: dict = field(default_factory=lambda: dict(DEFAULT_RISK_PRESETS))
    default_level: str = "medium"
    atr_stop_mult: float = 2.0  # stop distance = mult * ATR
    reward_risk_ratio: float = 2.0  # take-profit distance = R:R * stop distance
    max_open_positions: int = 3
    # Hard cap as a fraction of equity, regardless of preset.
    max_risk_pct: float = 0.05

    def risk_pct(self, level: str) -> float:
        return self.presets.get(level, self.presets[self.default_level])


@dataclass
class Credentials:
    """TradeLocker login credentials, sourced from the environment."""

    username: Optional[str] = None
    password: Optional[str] = None
    server: Optional[str] = None

    @property
    def complete(self) -> bool:
        return bool(self.username and self.password and self.server)


@dataclass
class Config:
    """Top-level application configuration."""

    live: bool = False
    watchlist: list = field(default_factory=lambda: list(DEFAULT_WATCHLIST))
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    credentials: Credentials = field(default_factory=Credentials)
    # Paper-trading starting balance, used when no broker is connected.
    paper_balance: float = 100_000.0

    @property
    def environment_url(self) -> str:
        return LIVE_URL if self.live else DEMO_URL

    @property
    def environment_name(self) -> str:
        return "LIVE" if self.live else "DEMO"


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_config(config_path: Optional[str] = None) -> Config:
    """Load configuration from YAML + environment.

    Environment variables (typically in a .env file):
      TRADELOCKER_USERNAME, TRADELOCKER_PASSWORD, TRADELOCKER_SERVER
      PROPSHIELD_LIVE = "1" / "true" to default to the live environment.
    """
    load_dotenv()

    root = Path(__file__).resolve().parent.parent
    path = Path(config_path) if config_path else root / "config" / "default.yaml"
    data = _load_yaml(path)

    cfg = Config()

    if "watchlist" in data and data["watchlist"]:
        cfg.watchlist = list(data["watchlist"])
    if "paper_balance" in data:
        cfg.paper_balance = float(data["paper_balance"])

    if "strategy" in data and data["strategy"]:
        cfg.strategy = StrategyConfig(**{**vars(StrategyConfig()), **data["strategy"]})
    if "risk" in data and data["risk"]:
        risk_data = dict(data["risk"])
        if "presets" in risk_data and risk_data["presets"]:
            risk_data["presets"] = {
                k: float(v) for k, v in risk_data["presets"].items()
            }
        cfg.risk = RiskConfig(**{**vars(RiskConfig()), **risk_data})

    # Credentials and environment toggle from the process environment.
    cfg.credentials = Credentials(
        username=os.getenv("TRADELOCKER_USERNAME"),
        password=os.getenv("TRADELOCKER_PASSWORD"),
        server=os.getenv("TRADELOCKER_SERVER"),
    )
    live_env = os.getenv("PROPSHIELD_LIVE", "").strip().lower()
    cfg.live = live_env in {"1", "true", "yes", "on"}

    return cfg
