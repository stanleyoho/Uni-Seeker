from pydantic import BaseModel


class LowBaseScoreResponse(BaseModel):
    symbol: str
    name: str
    total_score: float
    valuation_score: float
    price_position_score: float
    quality_score: float
    pe_percentile: float | None = None
    ma240_deviation: float | None = None
    peg: float | None = None
    details: dict[str, object]
    disqualified: bool = False
    disqualify_reason: str = ""


class LowBaseRankingResponse(BaseModel):
    results: list[LowBaseScoreResponse]
    total_scanned: int
    total_qualified: int
