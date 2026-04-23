from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PEPercentile:
    """PE ratio position in historical range."""
    current_pe: float
    percentile: float  # 0.0 - 1.0 (0 = lowest in history, 1 = highest)
    min_pe: float
    max_pe: float
    median_pe: float
    data_points: int


@dataclass(frozen=True)
class MADeviation:
    """Price deviation from moving average."""
    ma_value: float
    current_price: float
    deviation_pct: float  # (price - MA) / MA * 100, negative = below MA
    period: int


@dataclass(frozen=True)
class PEGRatio:
    """Price/Earnings to Growth ratio."""
    pe: float
    earnings_growth: float  # annual EPS growth %
    peg: float  # PE / growth. < 1 = undervalued


def calculate_pe_percentile(pe_history: list[float]) -> PEPercentile | None:
    """Calculate where current PE sits in historical distribution."""
    valid = [p for p in pe_history if p > 0]
    if len(valid) < 4:
        return None

    current = valid[-1]
    sorted_pe = sorted(valid)
    rank = sum(1 for p in sorted_pe if p <= current)
    percentile = rank / len(sorted_pe)

    return PEPercentile(
        current_pe=round(current, 2),
        percentile=round(percentile, 4),
        min_pe=round(sorted_pe[0], 2),
        max_pe=round(sorted_pe[-1], 2),
        median_pe=round(sorted_pe[len(sorted_pe) // 2], 2),
        data_points=len(valid),
    )


def calculate_ma_deviation(closes: list[float], period: int = 240) -> MADeviation | None:
    """Calculate price deviation from N-day moving average."""
    if len(closes) < period:
        return None

    ma = sum(closes[-period:]) / period
    current = closes[-1]
    deviation = (current - ma) / ma * 100

    return MADeviation(
        ma_value=round(ma, 2),
        current_price=round(current, 2),
        deviation_pct=round(deviation, 2),
        period=period,
    )


def calculate_peg(pe: float, earnings_growth_pct: float) -> PEGRatio | None:
    """Calculate PEG ratio. Growth should be in % (e.g., 15 for 15%)."""
    if pe <= 0 or earnings_growth_pct <= 0:
        return None

    peg = pe / earnings_growth_pct
    return PEGRatio(
        pe=round(pe, 2),
        earnings_growth=round(earnings_growth_pct, 2),
        peg=round(peg, 2),
    )
