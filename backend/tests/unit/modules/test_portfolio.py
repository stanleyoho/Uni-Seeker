from app.modules.backtester.portfolio import Portfolio


def test_buy() -> None:
    p = Portfolio(initial_capital=1_000_000)
    assert p.buy("2330.TW", 890.0, 100, "2026-04-22")
    assert p.positions["2330.TW"] == 100
    assert p.cash < 1_000_000


def test_buy_insufficient_cash() -> None:
    p = Portfolio(initial_capital=1_000)
    assert p.buy("2330.TW", 890.0, 100, "2026-04-22") is False
    assert "2330.TW" not in p.positions


def test_sell() -> None:
    p = Portfolio(initial_capital=1_000_000)
    p.buy("2330.TW", 890.0, 100, "2026-04-22")
    assert p.sell("2330.TW", 900.0, 100, "2026-04-23")
    assert "2330.TW" not in p.positions
    assert len(p.trades) == 2


def test_sell_insufficient_shares() -> None:
    p = Portfolio(initial_capital=1_000_000)
    assert p.sell("2330.TW", 890.0, 100, "2026-04-22") is False


def test_total_value() -> None:
    p = Portfolio(initial_capital=1_000_000)
    p.buy("2330.TW", 890.0, 100, "2026-04-22")
    value = p.total_value({"2330.TW": 900.0})
    # Cash + position value
    assert value > 0
    assert value != 1_000_000  # should differ due to fees


def test_equity_curve() -> None:
    p = Portfolio(initial_capital=1_000_000)
    p.record_equity({"2330.TW": 890.0})
    p.record_equity({"2330.TW": 900.0})
    assert len(p.equity_curve) == 2
    assert p.equity_curve[0] == 1_000_000  # no positions
