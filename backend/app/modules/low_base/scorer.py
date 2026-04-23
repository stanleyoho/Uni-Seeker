from dataclasses import dataclass, field

from app.modules.low_base.indicators import (
    PEPercentile,
    MADeviation,
    PEGRatio,
    calculate_pe_percentile,
    calculate_ma_deviation,
    calculate_peg,
)


@dataclass
class LowBaseScore:
    """Composite low-base score for a stock."""
    symbol: str
    name: str
    total_score: float  # 0-100

    # Sub-scores (each 0-100, then weighted)
    valuation_score: float  # 40% weight
    price_position_score: float  # 30% weight
    quality_score: float  # 30% weight

    # Detail data
    pe_percentile: PEPercentile | None = None
    ma_deviation: MADeviation | None = None
    peg_ratio: PEGRatio | None = None

    # Individual metrics used
    details: dict[str, object] = field(default_factory=dict)

    # Disqualification reason (if any)
    disqualified: bool = False
    disqualify_reason: str = ""


def _score_linear(value: float | None, best: float, worst: float) -> float:
    """Score linearly: value at 'best' -> 100, at 'worst' -> 0."""
    if value is None:
        return 50.0  # neutral
    if best == worst:
        return 50.0
    if best < worst:  # lower is better
        if value <= best:
            return 100.0
        if value >= worst:
            return 0.0
        return (worst - value) / (worst - best) * 100
    else:  # higher is better
        if value >= best:
            return 100.0
        if value <= worst:
            return 0.0
        return (value - worst) / (best - worst) * 100


def calculate_low_base_score(
    symbol: str,
    name: str,
    # Price data
    closes: list[float],
    # Valuation data
    pe: float | None = None,
    pb: float | None = None,
    dividend_yield: float | None = None,
    pe_history: list[float] | None = None,
    industry_avg_pe: float | None = None,
    # Quality data
    roe: float | None = None,
    debt_ratio: float | None = None,
    revenue_yoy_growth: float | None = None,
    eps: float | None = None,
    health_score: float | None = None,
    # Technical data
    rsi: float | None = None,
) -> LowBaseScore:
    """Calculate composite low-base score."""

    # === Disqualification checks ===
    if eps is not None and eps <= 0:
        return LowBaseScore(
            symbol=symbol, name=name, total_score=0,
            valuation_score=0, price_position_score=0, quality_score=0,
            disqualified=True, disqualify_reason="Negative EPS (虧損股排除)",
        )

    # === 1. Valuation Score (40%) ===
    val_components: list[float] = []
    details: dict[str, object] = {}

    # PE Percentile (lower = better for low base)
    pe_pct = None
    if pe_history and len(pe_history) >= 4:
        pe_pct = calculate_pe_percentile(pe_history)
        if pe_pct:
            # PE in bottom 25% = 100, top 75% = 0
            val_components.append(_score_linear(pe_pct.percentile, 0.0, 0.75))
            details["pe_percentile"] = pe_pct.percentile

    # PE vs Industry
    if pe and industry_avg_pe and industry_avg_pe > 0:
        pe_vs_industry = pe / industry_avg_pe
        # 0.5x industry PE = 100, 1.5x = 0
        val_components.append(_score_linear(pe_vs_industry, 0.5, 1.5))
        details["pe_vs_industry"] = round(pe_vs_industry, 2)

    # PB (lower = better)
    if pb is not None:
        val_components.append(_score_linear(pb, 0.5, 3.0))
        details["pb"] = pb

    # Dividend yield (higher = better for value)
    if dividend_yield is not None:
        val_components.append(_score_linear(dividend_yield, 8.0, 0.0))
        details["dividend_yield"] = dividend_yield

    valuation_score = sum(val_components) / len(val_components) if val_components else 50.0

    # === 2. Price Position Score (30%) ===
    price_components: list[float] = []

    # MA240 deviation (below MA = good for low base)
    ma_dev = None
    if len(closes) >= 240:
        ma_dev = calculate_ma_deviation(closes, 240)
        if ma_dev:
            # -20% below MA = 100, +20% above = 0
            # But below -30% is dangerous, cap at -30%
            dev = max(ma_dev.deviation_pct, -30.0)
            price_components.append(_score_linear(dev, -20.0, 20.0))
            details["ma240_deviation"] = ma_dev.deviation_pct

    # MA60 deviation
    if len(closes) >= 60:
        ma60 = calculate_ma_deviation(closes, 60)
        if ma60:
            price_components.append(_score_linear(ma60.deviation_pct, -15.0, 15.0))
            details["ma60_deviation"] = ma60.deviation_pct

    # RSI (lower = more oversold = better for low base)
    if rsi is not None:
        price_components.append(_score_linear(rsi, 20.0, 70.0))
        details["rsi"] = rsi

    # Price drop from recent high (moderate drop = good, extreme = risky)
    if len(closes) >= 240:
        high_240 = max(closes[-240:])
        drop_pct = (closes[-1] - high_240) / high_240 * 100
        # -25% drop = 100, 0% drop = 0, but < -50% = 20 (too risky)
        if drop_pct < -50:
            price_components.append(20.0)
        else:
            price_components.append(_score_linear(drop_pct, -25.0, 0.0))
        details["drop_from_high_240d"] = round(drop_pct, 2)

    price_position_score = sum(price_components) / len(price_components) if price_components else 50.0

    # === 3. Quality Score (30%) ===
    quality_components: list[float] = []

    # ROE (higher = better)
    if roe is not None:
        quality_components.append(_score_linear(roe, 0.20, 0.0))
        details["roe"] = roe

    # Debt ratio (lower = better)
    if debt_ratio is not None:
        quality_components.append(_score_linear(debt_ratio, 0.2, 0.7))
        details["debt_ratio"] = debt_ratio

    # Revenue YoY growth (positive = better)
    if revenue_yoy_growth is not None:
        quality_components.append(_score_linear(revenue_yoy_growth, 20.0, -10.0))
        details["revenue_yoy_growth"] = revenue_yoy_growth

    # Health score
    if health_score is not None:
        quality_components.append(health_score)  # already 0-100
        details["health_score"] = health_score

    # PEG ratio (< 1 = undervalued growth)
    peg = None
    if pe and revenue_yoy_growth and revenue_yoy_growth > 0:
        peg = calculate_peg(pe, revenue_yoy_growth)
        if peg:
            quality_components.append(_score_linear(peg.peg, 0.5, 2.0))
            details["peg"] = peg.peg

    quality_score = sum(quality_components) / len(quality_components) if quality_components else 50.0

    # === Composite ===
    total = valuation_score * 0.4 + price_position_score * 0.3 + quality_score * 0.3

    return LowBaseScore(
        symbol=symbol,
        name=name,
        total_score=round(total, 2),
        valuation_score=round(valuation_score, 2),
        price_position_score=round(price_position_score, 2),
        quality_score=round(quality_score, 2),
        pe_percentile=pe_pct,
        ma_deviation=ma_dev,
        peg_ratio=peg,
        details=details,
    )
