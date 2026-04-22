from app.modules.notifier.templates import (
    format_post_market_summary,
    format_price_alert,
    format_screener_hit,
)


def test_price_alert_format() -> None:
    msg = format_price_alert(symbol="2330.TW", name="台積電", price=890.0, condition="上穿 $890")
    assert "2330.TW" in msg
    assert "台積電" in msg
    assert "890" in msg


def test_post_market_summary_format() -> None:
    holdings = [
        {"symbol": "2330.TW", "name": "台積電", "price": 890.0, "change_pct": 2.3},
        {"symbol": "2317.TW", "name": "鴻海", "price": 178.0, "change_pct": -0.5},
    ]
    hits = [
        {"strategy": "超跌反彈", "symbol": "2412.TW", "name": "中華電", "detail": "RSI: 28.5"},
    ]
    msg = format_post_market_summary(
        market="台股", date="2026-04-22", holdings=holdings, screener_hits=hits,
    )
    assert "盤後總結" in msg
    assert "台積電" in msg
    assert "+2.3%" in msg
    assert "超跌反彈" in msg


def test_screener_hit_format() -> None:
    msg = format_screener_hit(
        strategy="低基期", symbol="3034.TW", name="聯詠", detail="PE: 11.2, 產業均: 18.5",
    )
    assert "低基期" in msg
    assert "3034.TW" in msg
