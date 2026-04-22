from decimal import Decimal
from datetime import date
from app.modules.valuation.base import ValuationData
from app.modules.screener.industry import IndustryScreener

def _make_valuations() -> list[ValuationData]:
    return [
        ValuationData(symbol="2330.TW", name="台積電", date=date(2026, 4, 22),
                      pe_ratio=Decimal("22.5"), pb_ratio=Decimal("5.6"),
                      dividend_yield=Decimal("1.8"), industry="半導體業"),
        ValuationData(symbol="2303.TW", name="聯電", date=date(2026, 4, 22),
                      pe_ratio=Decimal("10.5"), pb_ratio=Decimal("1.2"),
                      dividend_yield=Decimal("5.0"), industry="半導體業"),
        ValuationData(symbol="3034.TW", name="聯詠", date=date(2026, 4, 22),
                      pe_ratio=Decimal("11.2"), pb_ratio=Decimal("2.8"),
                      dividend_yield=Decimal("4.5"), industry="半導體業"),
        ValuationData(symbol="2317.TW", name="鴻海", date=date(2026, 4, 22),
                      pe_ratio=Decimal("12.0"), pb_ratio=Decimal("0.7"),
                      dividend_yield=Decimal("6.5"), industry="其他電子業"),
        ValuationData(symbol="9999.TW", name="虧損公司", date=date(2026, 4, 22),
                      pe_ratio=None, pb_ratio=Decimal("0.5"),
                      dividend_yield=None, industry="半導體業"),
    ]

def test_industry_averages() -> None:
    screener = IndustryScreener()
    avgs = screener.compute_industry_averages(_make_valuations())
    semi = avgs["半導體業"]
    assert semi.avg_pe is not None
    assert abs(float(semi.avg_pe) - 14.73) < 0.1

def test_find_undervalued() -> None:
    screener = IndustryScreener()
    results = screener.find_undervalued(_make_valuations(), z_threshold=-0.5)
    symbols = [r.symbol for r in results]
    assert "2303.TW" in symbols
    assert "3034.TW" in symbols
    assert "2330.TW" not in symbols

def test_excludes_negative_eps() -> None:
    screener = IndustryScreener()
    results = screener.find_undervalued(_make_valuations())
    symbols = [r.symbol for r in results]
    assert "9999.TW" not in symbols

def test_result_has_z_score() -> None:
    screener = IndustryScreener()
    results = screener.find_undervalued(_make_valuations(), z_threshold=-0.5)
    for r in results:
        assert r.pe_z_score is not None
        assert r.pe_z_score < 0

def test_results_sorted_by_score() -> None:
    screener = IndustryScreener()
    results = screener.find_undervalued(_make_valuations(), z_threshold=-0.5)
    if len(results) >= 2:
        assert results[0].score >= results[1].score
