from propshield.broker.paper import PaperBroker
from propshield.models import Side


def _broker():
    b = PaperBroker(starting_balance=50_000.0)
    b.connect()
    return b


def test_account_state_initial():
    b = _broker()
    acct = b.get_account_state()
    assert acct.balance == 50_000.0
    assert acct.equity == 50_000.0
    assert acct.open_positions == 0


def test_instruments_nonempty_and_resolvable():
    b = _broker()
    assert len(b.get_instruments()) > 0
    assert b.resolve_instrument("US30") is not None
    assert b.resolve_instrument("nas100") is not None  # case-insensitive


def test_price_history_shape():
    b = _broker()
    ins = b.resolve_instrument("US30")
    df = b.get_price_history(ins, "1H", "1M")
    assert {"open", "high", "low", "close", "volume"} <= set(df.columns)
    assert len(df) > 200
    assert (df["high"] >= df["low"]).all()


def test_price_history_deterministic():
    a = _broker().get_price_history(_broker().resolve_instrument("US30"), "1H", "5D")
    b = _broker().get_price_history(_broker().resolve_instrument("US30"), "1H", "5D")
    assert a["close"].iloc[-1] == b["close"].iloc[-1]


def test_open_and_close_position_updates_count():
    b = _broker()
    ins = b.resolve_instrument("US30")
    pid = b.place_order(ins, Side.BUY, quantity=1.0, stop_loss=1.0, take_profit=2.0)
    assert b.get_account_state().open_positions == 1
    positions = b.get_positions()
    assert len(positions) == 1 and positions[0].position_id == pid
    b.close_position(pid)
    assert b.get_account_state().open_positions == 0
