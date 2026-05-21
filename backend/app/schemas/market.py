from pydantic import BaseModel
from app.schemas.types import DecimalStr

class MarketMover(BaseModel):
    symbol: str
    name: str
    market: str
    close: DecimalStr
    change: DecimalStr
    change_percent: DecimalStr
    volume: int

class MarketMoversResponse(BaseModel):
    gainers: list[MarketMover]
    losers: list[MarketMover]
    most_active: list[MarketMover]
    date: str | None

class MarketIndex(BaseModel):
    symbol: str
    name: str
    value: DecimalStr
    change: DecimalStr
    change_percent: DecimalStr

class MarketIndicesResponse(BaseModel):
    indices: list[MarketIndex]

class HeatmapStock(BaseModel):
    symbol: str
    name: str
    close: DecimalStr
    change_percent: DecimalStr
    volume: int

class HeatmapSector(BaseModel):
    industry: str
    stock_count: int
    avg_change_percent: DecimalStr
    total_volume: int
    stocks: list[HeatmapStock]

class HeatmapResponse(BaseModel):
    sectors: list[HeatmapSector]
    date: str | None
