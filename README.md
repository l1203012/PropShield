# PropShield

A terminal-first **indices trading bot** for the [TradeLocker](https://tradelocker.com)
platform. PropShield scouts a watchlist of index instruments with a
multi-indicator scoring strategy, sizes positions by a percentage of account
equity, and executes trades on TradeLocker — in a **paper**, **demo**, or
**live** environment.

> ⚠️ **Trading involves risk of loss.** Live mode trades real money. Validate
> any strategy in paper/demo first. This software is provided as-is, with no
> warranty or guarantee of profit.

## Features

- **Advanced scouting** — ranks every index in the watchlist by a composite
  0–100 conviction score combining trend (EMA 21/50/200), momentum (MACD, RSI),
  and volatility/breakout (ATR, Bollinger %B, range position).
- **Risk selection** — pick `low` / `medium` / `high`, mapping to a configurable
  % of equity risked per trade (default 0.5% / 1% / 2%). Position size is derived
  from an ATR-based stop so each trade risks exactly that budget.
- **Three environments** — fully offline **paper** simulator (no credentials
  needed), TradeLocker **demo**, and **live** (with an explicit confirmation
  gate before any real-money order).
- **Safety rails** — minimum-score threshold, max open positions, hard cap on
  risk %, and a "type LIVE to confirm" gate for live orders.
- **Pluggable design** — broker, strategy, and risk layers are decoupled behind
  clean interfaces, so new strategies or brokers slot in without rewrites.

## Architecture

```
propshield/
├── cli.py            # argument parsing + entry point (python -m propshield)
├── terminal.py       # interactive rich UI
├── engine.py         # orchestration: scan → rank → size → execute
├── factory.py        # wires broker + strategy + risk together
├── config.py         # YAML + .env configuration
├── models.py         # dataclasses (Instrument, Signal, TradePlan, …)
├── indicators.py     # EMA, RSI, ATR, MACD, Bollinger (pure pandas/numpy)
├── risk.py           # % equity position sizing
├── strategy/
│   ├── base.py       # Strategy interface
│   └── scout.py      # multi-indicator scoring scout
└── broker/
    ├── base.py       # Broker interface
    ├── paper.py      # offline simulator (synthetic OHLCV)
    └── tradelocker_client.py  # official tradelocker SDK wrapper
```

The **broker abstraction** means the strategy/risk/UI never depend on
TradeLocker directly — the offline `PaperBroker` and the live
`TradeLockerBroker` are interchangeable.

## Quick start

```bash
# 1. Create a virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Run fully offline against the paper simulator (no credentials needed)
python -m propshield --paper

# 3. Or run a single scout scan and exit
python -m propshield --paper --scan-once
```

### Connecting to TradeLocker (demo / live)

```bash
cp .env.example .env      # then fill in your credentials
python -m propshield --demo      # TradeLocker demo environment
python -m propshield --live      # TradeLocker live environment (real funds)
```

`.env` holds your TradeLocker `username`, `password`, and `server`. With no
explicit `--paper/--demo/--live` flag, PropShield uses the live broker if
credentials are present and falls back to the paper simulator otherwise.

## Using the terminal

| Option | Action |
|--------|--------|
| `1` | **Scout indices** — scan the watchlist and print a ranked table |
| `2` | **Set risk level** — choose low / medium / high |
| `3` | **Trade a setup** — pick a ranked setup (or `b` for best), review the sized plan, confirm |
| `4` | **Positions** — list open positions with unrealized P&L |
| `5` | **Close position** — close by ID |
| `6` | **Refresh** — re-read account state |
| `q` | **Quit** |

## Configuration

Strategy, risk, and watchlist parameters live in
[`config/default.yaml`](config/default.yaml). Credentials and the environment
toggle come from `.env`. Point at a different file with `--config path.yaml`.

Key knobs:

- `strategy.resolution` / `lookback_period` — timeframe and history depth
- `strategy.min_score` — minimum conviction to count as tradable
- `risk.presets` — % equity risked per level
- `risk.atr_stop_mult` — stop distance as a multiple of ATR
- `risk.reward_risk_ratio` — take-profit distance relative to stop
- `risk.max_open_positions` / `max_risk_pct` — safety caps

## How the scout scores a setup

For each instrument the scout computes a panel of indicators and combines them
into one signed conviction score (weights are configurable in code):

| Component | Weight | Reads |
|-----------|--------|-------|
| Short-term trend | 25% | EMA fast vs slow separation |
| Long-term trend | 20% | price vs EMA(200) |
| MACD momentum | 20% | histogram, ATR-normalised |
| RSI momentum | 15% | distance from 50, dampened at extremes |
| Breakout | 12% | position within the recent high/low range |
| Bollinger | 8% | %B position within bands |

The **sign** of the weighted net decides direction (long/short); its
**magnitude** (0–100) is the conviction score. Setups where short- and
long-term trends disagree with the chosen direction are penalised.

## Development

```bash
pip install -r requirements.txt
pytest                  # run the test suite (27 tests)
```

## Branches

- `main` — stable
- `staging` — integration / pre-release testing

## Disclaimer

PropShield is an educational/personal trading tool. It is not financial advice.
Use at your own risk; never trade funds you cannot afford to lose.
