from app.modules.revenue.base import RevenueRecord, RevenueProvider
from app.modules.revenue.analyzer import analyze_revenue


def _make_records(revenues: list[float], start_year: int = 2024) -> list[RevenueRecord]:
    records = []
    for i, rev in enumerate(revenues):
        q = (i % 4) + 1
        y = start_year + i // 4
        records.append(RevenueRecord(
            symbol="TEST", period=f"{y}-Q{q}",
            period_type="quarterly", revenue=rev,
        ))
    return records


def test_analyze_growing_revenue() -> None:
    records = _make_records([100, 110, 120, 130, 140, 150, 160, 170])
    analysis = analyze_revenue(records)
    assert analysis is not None
    assert analysis.yoy_growth is not None
    assert analysis.yoy_growth > 0
    assert analysis.trend == "up"
    assert analysis.is_revenue_high is True


def test_analyze_declining_revenue() -> None:
    records = _make_records([170, 160, 150, 140, 130, 120, 110, 100])
    analysis = analyze_revenue(records)
    assert analysis is not None
    assert analysis.trend == "down"
    assert analysis.is_revenue_low is True


def test_analyze_qoq_growth() -> None:
    records = _make_records([100, 120])
    analysis = analyze_revenue(records)
    assert analysis is not None
    assert analysis.qoq_growth == 20.0  # (120-100)/100*100


def test_analyze_empty() -> None:
    assert analyze_revenue([]) is None


def test_consecutive_growth() -> None:
    # 8 quarters: each year has higher revenue than prev year same quarter
    records = _make_records([100, 110, 120, 130, 140, 150, 160, 170])
    analysis = analyze_revenue(records)
    assert analysis is not None
    assert analysis.consecutive_growth_quarters >= 1


def test_revenue_provider_protocol() -> None:
    from app.modules.revenue.yfinance_revenue import YFinanceRevenueProvider
    assert isinstance(YFinanceRevenueProvider(), RevenueProvider)
