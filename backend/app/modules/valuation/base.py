from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ValuationData:
    symbol: str
    name: str
    date: date
    pe_ratio: Decimal | None
    pb_ratio: Decimal | None
    dividend_yield: Decimal | None
    industry: str = ""


@runtime_checkable
class ValuationProvider(Protocol):
    async def fetch_valuations(self) -> list[ValuationData]: ...
