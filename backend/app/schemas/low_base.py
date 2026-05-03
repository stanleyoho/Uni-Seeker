from pydantic import BaseModel
from app.schemas.types import DecimalStr


class LowBaseScoreResponse(BaseModel):
    symbol: str
    name: str
    total_score: DecimalStr
    valuation_score: DecimalStr
    price_position_score: DecimalStr
    quality_score: DecimalStr
    institutional_technical_score: DecimalStr | None = None
    pe_percentile: DecimalStr | None = None
    ma240_deviation: DecimalStr | None = None
    peg: DecimalStr | None = None
    details: dict[str, object]
    disqualified: bool = False
    disqualify_reason: str = ""


class LowBaseRankingResponse(BaseModel):
    results: list[LowBaseScoreResponse]
    total_scanned: int
    total_qualified: int
