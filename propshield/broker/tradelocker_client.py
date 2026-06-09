"""TradeLocker broker implementation backed by the official ``tradelocker`` SDK.

This wraps :class:`tradelocker.TLAPI` behind the :class:`~propshield.broker.base.Broker`
interface. The SDK returns pandas DataFrames/dicts whose column names can vary
slightly between broker configurations, so accessors here are defensive and
fall back gracefully.

The ``tradelocker`` import is done lazily inside :meth:`connect` so the rest of
the bot (and the paper broker) works even if the SDK is not installed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from propshield.broker.base import Broker
from propshield.models import AccountState, Instrument, Position, Quote, Side


def _first_present(row: Any, keys: list[str], default: Any = None) -> Any:
    """Return the first key present in a dict-like / Series row."""
    for key in keys:
        try:
            if key in row and pd.notna(row[key]):
                return row[key]
        except (TypeError, KeyError):
            continue
    return default


class TradeLockerBroker(Broker):
    """Live/demo broker using the TradeLocker REST API."""

    name = "tradelocker"

    def __init__(
        self,
        environment: str,
        username: str,
        password: str,
        server: str,
        log_level: str = "warning",
    ):
        self._environment = environment
        self._username = username
        self._password = password
        self._server = server
        self._log_level = log_level
        self._api = None
        self._instruments_cache: Optional[list[Instrument]] = None

    # -- lifecycle -----------------------------------------------------------
    def connect(self) -> None:
        if self._api is not None:
            return
        try:
            from tradelocker import TLAPI
        except ImportError as exc:  # pragma: no cover - depends on env
            raise RuntimeError(
                "The 'tradelocker' package is required for live/demo trading. "
                "Install it with: pip install tradelocker"
            ) from exc

        self._api = TLAPI(
            environment=self._environment,
            username=self._username,
            password=self._password,
            server=self._server,
            log_level=self._log_level,  # type: ignore[arg-type]
        )

    def _require(self):
        if self._api is None:
            self.connect()
        return self._api

    # -- account -------------------------------------------------------------
    def get_account_state(self) -> AccountState:
        state = self._require().get_account_state()
        # get_account_state returns a dict keyed by metric name.
        balance = float(_first_present(state, ["balance", "cashBalance"], 0.0))
        equity = float(
            _first_present(
                state, ["projectedBalance", "equity", "balance"], balance
            )
        )
        open_positions = int(_first_present(state, ["positionsCount"], 0) or 0)
        return AccountState(
            balance=balance,
            equity=equity,
            currency="USD",
            open_positions=open_positions,
        )

    # -- instruments ---------------------------------------------------------
    def get_instruments(self) -> list[Instrument]:
        if self._instruments_cache is not None:
            return self._instruments_cache
        df = self._require().get_all_instruments()
        instruments: list[Instrument] = []
        for _, row in df.iterrows():
            ins_id = _first_present(
                row, ["tradableInstrumentId", "instrumentId", "id"]
            )
            symbol = _first_present(row, ["name", "symbol", "ticker"], "")
            if ins_id is None or not symbol:
                continue
            instruments.append(
                Instrument(
                    instrument_id=int(ins_id),
                    symbol=str(symbol),
                    name=str(_first_present(row, ["description", "name"], symbol)),
                )
            )
        self._instruments_cache = instruments
        return instruments

    # -- market data ---------------------------------------------------------
    def get_price_history(
        self, instrument: Instrument, resolution: str, lookback_period: str
    ) -> pd.DataFrame:
        df = self._require().get_price_history(
            instrument_id=instrument.instrument_id,
            resolution=resolution,
            lookback_period=lookback_period,
        )
        if df is None or len(df) == 0:
            return pd.DataFrame(
                columns=["open", "high", "low", "close", "volume"]
            )
        # SDK returns columns t (ms epoch), o, h, l, c, v.
        out = pd.DataFrame(
            {
                "open": df.get("o", df.get("open")),
                "high": df.get("h", df.get("high")),
                "low": df.get("l", df.get("low")),
                "close": df.get("c", df.get("close")),
                "volume": df.get("v", df.get("volume", 0.0)),
            }
        )
        ts = df.get("t", df.get("timestamp"))
        if ts is not None:
            out.index = pd.to_datetime(ts, unit="ms")
        return out.dropna(subset=["close"])

    def get_quote(self, instrument: Instrument) -> Quote:
        api = self._require()
        ask = float(api.get_latest_asking_price(instrument.instrument_id))
        bid = ask
        if hasattr(api, "get_latest_bid_price"):
            try:
                bid = float(api.get_latest_bid_price(instrument.instrument_id))
            except Exception:  # pragma: no cover - network dependent
                bid = ask
        return Quote(
            symbol=instrument.symbol,
            bid=bid,
            ask=ask,
            timestamp=datetime.now(timezone.utc),
        )

    # -- trading -------------------------------------------------------------
    def place_order(
        self,
        instrument: Instrument,
        side: Side,
        quantity: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> str:
        api = self._require()
        order_id = api.create_order(
            instrument_id=instrument.instrument_id,
            quantity=quantity,
            side=side.value,
            type_="market",
            stop_loss=stop_loss,
            stop_loss_type="absolute" if stop_loss is not None else None,
            take_profit=take_profit,
            take_profit_type="absolute" if take_profit is not None else None,
        )
        if order_id is None:
            raise RuntimeError(
                f"Order rejected by TradeLocker for {instrument.symbol}"
            )
        return str(order_id)

    def get_positions(self) -> list[Position]:
        df = self._require().get_all_positions()
        if df is None or len(df) == 0:
            return []
        positions: list[Position] = []
        instruments = {i.instrument_id: i for i in self.get_instruments()}
        for _, row in df.iterrows():
            ins_id = _first_present(row, ["tradableInstrumentId", "instrumentId"])
            symbol = ""
            if ins_id is not None and int(ins_id) in instruments:
                symbol = instruments[int(ins_id)].symbol
            side_raw = str(_first_present(row, ["side"], "buy")).lower()
            positions.append(
                Position(
                    position_id=str(_first_present(row, ["id", "positionId"], "")),
                    symbol=symbol,
                    side=Side.BUY if side_raw == "buy" else Side.SELL,
                    quantity=float(_first_present(row, ["qty", "quantity"], 0.0)),
                    entry_price=float(
                        _first_present(row, ["avgPrice", "openPrice"], 0.0)
                    ),
                    stop_loss=_first_present(row, ["stopLoss"]),
                    take_profit=_first_present(row, ["takeProfit"]),
                    unrealized_pnl=float(
                        _first_present(row, ["unrealizedPl", "unrealizedPnl"], 0.0)
                    ),
                )
            )
        return positions

    def close_position(self, position_id: str) -> None:
        ok = self._require().close_position(position_id=int(position_id))
        if not ok:
            raise RuntimeError(f"Failed to close position {position_id}")
