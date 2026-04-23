from dataclasses import dataclass

from app.modules.financial_analysis.ratios import FinancialRatios


@dataclass
class HealthScore:
    symbol: str
    period: str
    total_score: float  # 0-100
    profitability_score: float  # 0-25
    efficiency_score: float  # 0-25
    leverage_score: float  # 0-25
    growth_score: float  # 0-25
    details: dict[str, str]  # explanation per category


def _score_range(value: float | None, bad: float, good: float, max_score: float = 25.0) -> float:
    """Score a value linearly between bad (0) and good (max_score)."""
    if value is None:
        return max_score * 0.5  # neutral if no data
    if good > bad:
        if value >= good:
            return max_score
        if value <= bad:
            return 0
        return round((value - bad) / (good - bad) * max_score, 2)
    else:
        if value <= good:
            return max_score
        if value >= bad:
            return 0
        return round((bad - value) / (bad - good) * max_score, 2)


def calculate_health_score(ratios: FinancialRatios) -> HealthScore:
    """Calculate composite health score (0-100) from financial ratios."""
    details: dict[str, str] = {}

    # Profitability (0-25)
    gm = _score_range(ratios.gross_margin, 0.0, 0.4, 8)
    om = _score_range(ratios.operating_margin, -0.05, 0.2, 8)
    roe_s = _score_range(ratios.roe, 0.0, 0.2, 9)
    profitability = round(gm + om + roe_s, 2)
    details["profitability"] = f"GM:{ratios.gross_margin} OM:{ratios.operating_margin} ROE:{ratios.roe}"

    # Efficiency (0-25)
    it = _score_range(ratios.inventory_turnover, 1.0, 10.0, 12)
    rt = _score_range(ratios.receivable_turnover, 2.0, 12.0, 13)
    efficiency = round(it + rt, 2)
    details["efficiency"] = f"InvTurn:{ratios.inventory_turnover} RecTurn:{ratios.receivable_turnover}"

    # Leverage (0-25) -- lower debt is better
    cr = _score_range(ratios.current_ratio, 0.5, 2.0, 10)
    dr = _score_range(ratios.debt_ratio, 0.8, 0.3, 15)  # reversed: lower is better
    leverage = round(cr + dr, 2)
    details["leverage"] = f"CR:{ratios.current_ratio} DR:{ratios.debt_ratio}"

    # Growth (0-25)
    rg = _score_range(ratios.revenue_growth, -0.1, 0.2, 12)
    nig = _score_range(ratios.net_income_growth, -0.2, 0.3, 13)
    growth = round(rg + nig, 2)
    details["growth"] = f"RevG:{ratios.revenue_growth} NIGrowth:{ratios.net_income_growth}"

    total = round(profitability + efficiency + leverage + growth, 2)

    return HealthScore(
        symbol=ratios.symbol,
        period=ratios.period,
        total_score=min(total, 100),
        profitability_score=profitability,
        efficiency_score=efficiency,
        leverage_score=leverage,
        growth_score=growth,
        details=details,
    )
