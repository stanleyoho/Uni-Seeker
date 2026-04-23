from dataclasses import dataclass

from app.modules.revenue.base import RevenueRecord


@dataclass
class RevenueAnalysis:
    symbol: str
    latest_revenue: float
    qoq_growth: float | None  # quarter-over-quarter %
    yoy_growth: float | None  # year-over-year %
    is_revenue_high: bool  # new revenue high in last 8 quarters
    is_revenue_low: bool  # new revenue low in last 8 quarters
    trend: str  # "up", "down", "flat"
    consecutive_growth_quarters: int  # consecutive YoY growth quarters


def analyze_revenue(records: list[RevenueRecord]) -> RevenueAnalysis | None:
    """Analyze revenue growth patterns."""
    if not records:
        return None

    # Sort by period ascending for analysis
    sorted_records = sorted(records, key=lambda r: r.period)
    latest = sorted_records[-1]

    # QoQ growth
    qoq = None
    if len(sorted_records) >= 2:
        prev = sorted_records[-2].revenue
        if prev > 0:
            qoq = round((latest.revenue - prev) / prev * 100, 2)

    # YoY growth (compare with 4 quarters ago)
    yoy = None
    if len(sorted_records) >= 5:
        prev_year = sorted_records[-5].revenue
        if prev_year > 0:
            yoy = round((latest.revenue - prev_year) / prev_year * 100, 2)

    # Revenue high/low in last 8 quarters
    recent = sorted_records[-8:] if len(sorted_records) >= 8 else sorted_records
    revenues = [r.revenue for r in recent]
    is_high = latest.revenue >= max(revenues)
    is_low = latest.revenue <= min(revenues)

    # Trend: compare last 4 quarters
    if len(sorted_records) >= 4:
        last4 = [r.revenue for r in sorted_records[-4:]]
        ups = sum(1 for i in range(1, len(last4)) if last4[i] > last4[i - 1])
        if ups >= 3:
            trend = "up"
        elif ups <= 0:
            trend = "down"
        else:
            trend = "flat"
    else:
        trend = "flat"

    # Consecutive YoY growth
    consecutive = 0
    if len(sorted_records) >= 5:
        for i in range(len(sorted_records) - 1, 3, -1):
            curr = sorted_records[i].revenue
            prev_y = sorted_records[i - 4].revenue
            if prev_y > 0 and curr > prev_y:
                consecutive += 1
            else:
                break

    return RevenueAnalysis(
        symbol=latest.symbol,
        latest_revenue=latest.revenue,
        qoq_growth=qoq,
        yoy_growth=yoy,
        is_revenue_high=is_high,
        is_revenue_low=is_low,
        trend=trend,
        consecutive_growth_quarters=consecutive,
    )
