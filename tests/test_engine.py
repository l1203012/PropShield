from propshield.config import Config
from propshield.factory import build_engine


def _engine():
    cfg = Config()
    return build_engine(cfg, paper=True)


def test_resolve_watchlist():
    eng = _engine()
    instruments = eng.resolve_watchlist()
    assert len(instruments) > 0


def test_scan_produces_results_and_ranking():
    eng = _engine()
    results = eng.scan()
    assert len(results) > 0
    ranked = eng.rank(results)
    # Ranked signals are sorted descending by score.
    scores = [s.score for s in ranked]
    assert scores == sorted(scores, reverse=True)


def test_full_cycle_scan_plan_execute():
    eng = _engine()
    results = eng.scan()
    ranked = eng.rank(results)
    assert ranked, "expected at least one signal from paper data"
    top = ranked[0]
    plan = eng.plan(top, "medium")
    assert plan.quantity > 0
    order_id = eng.execute(plan)
    assert order_id
    # Position should now be open.
    assert eng.account().open_positions == 1


def test_position_cap_enforced():
    cfg = Config()
    cfg.risk.max_open_positions = 1
    eng = build_engine(cfg, paper=True)
    results = eng.scan()
    ranked = eng.rank(results)
    plan = eng.plan(ranked[0], "low")
    eng.execute(plan)
    # Second execution should be blocked by the cap.
    try:
        eng.execute(eng.plan(ranked[0], "low"))
        assert False, "expected position cap to block second trade"
    except RuntimeError:
        pass
