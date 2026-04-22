import statistics
from dataclasses import dataclass
from decimal import Decimal
from app.modules.valuation.base import ValuationData


@dataclass
class IndustryAverage:
    industry: str
    avg_pe: Decimal | None
    avg_pb: Decimal | None
    avg_yield: Decimal | None
    std_pe: float
    count: int


@dataclass
class IndustryScreenResult:
    symbol: str
    name: str
    industry: str
    pe_ratio: Decimal
    industry_avg_pe: Decimal
    pe_z_score: float
    score: float


class IndustryScreener:
    def compute_industry_averages(self, valuations: list[ValuationData]) -> dict[str, IndustryAverage]:
        industry_data: dict[str, list[ValuationData]] = {}
        for v in valuations:
            if v.pe_ratio is not None and v.pe_ratio > 0:
                industry_data.setdefault(v.industry, []).append(v)

        averages: dict[str, IndustryAverage] = {}
        for industry, stocks in industry_data.items():
            pe_values = [float(s.pe_ratio) for s in stocks if s.pe_ratio is not None]
            pb_values = [float(s.pb_ratio) for s in stocks if s.pb_ratio is not None]
            dy_values = [float(s.dividend_yield) for s in stocks if s.dividend_yield is not None]

            avg_pe = Decimal(str(round(statistics.mean(pe_values), 4))) if pe_values else None
            avg_pb = Decimal(str(round(statistics.mean(pb_values), 4))) if pb_values else None
            avg_dy = Decimal(str(round(statistics.mean(dy_values), 4))) if dy_values else None
            std_pe = statistics.stdev(pe_values) if len(pe_values) >= 2 else 0.0

            averages[industry] = IndustryAverage(
                industry=industry, avg_pe=avg_pe, avg_pb=avg_pb,
                avg_yield=avg_dy, std_pe=std_pe, count=len(stocks),
            )
        return averages

    def find_undervalued(self, valuations: list[ValuationData], z_threshold: float = -1.0) -> list[IndustryScreenResult]:
        averages = self.compute_industry_averages(valuations)
        results: list[IndustryScreenResult] = []

        for v in valuations:
            if v.pe_ratio is None or v.pe_ratio <= 0:
                continue
            if v.industry not in averages:
                continue
            avg = averages[v.industry]
            if avg.avg_pe is None or avg.std_pe == 0:
                continue

            z_score = (float(v.pe_ratio) - float(avg.avg_pe)) / avg.std_pe
            if z_score <= z_threshold:
                score = abs(z_score)
                results.append(IndustryScreenResult(
                    symbol=v.symbol, name=v.name, industry=v.industry,
                    pe_ratio=v.pe_ratio, industry_avg_pe=avg.avg_pe,
                    pe_z_score=round(z_score, 4), score=round(score, 4),
                ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results
