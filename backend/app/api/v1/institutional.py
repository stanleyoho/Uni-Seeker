"""API endpoints for institutional investor (三大法人) buy/sell data."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.modules.finmind.institutional_provider import FinMindInstitutionalProvider

router = APIRouter(prefix="/institutional", tags=["institutional"])

# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------


class InstitutionalDayRecord(BaseModel):
    date: str
    foreign_buy: int
    foreign_sell: int
    foreign_net: int
    trust_buy: int
    trust_sell: int
    trust_net: int
    dealer_buy: int
    dealer_sell: int
    dealer_net: int
    total_net: int


class InstitutionalResponse(BaseModel):
    symbol: str
    data: list[InstitutionalDayRecord]


# ---------------------------------------------------------------------------
# Name mapping: FinMind name -> category
# ---------------------------------------------------------------------------

_CATEGORY_MAP: dict[str, str] = {
    "Foreign_Investor": "foreign",
    "Investment_Trust": "trust",
    "Dealer_self": "dealer",
    "Dealer_Hedging": "dealer",
}


def _aggregate(raw: list[dict[str, Any]]) -> list[InstitutionalDayRecord]:
    """Aggregate raw FinMind records by date, merging investor categories."""
    buckets: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "foreign_buy": 0,
            "foreign_sell": 0,
            "trust_buy": 0,
            "trust_sell": 0,
            "dealer_buy": 0,
            "dealer_sell": 0,
        }
    )

    for row in raw:
        cat = _CATEGORY_MAP.get(row.get("name", ""))
        if cat is None:
            continue
        date_str = row["date"]
        buckets[date_str][f"{cat}_buy"] += int(row.get("buy", 0))
        buckets[date_str][f"{cat}_sell"] += int(row.get("sell", 0))

    results: list[InstitutionalDayRecord] = []
    for date_str in sorted(buckets):
        b = buckets[date_str]
        foreign_net = b["foreign_buy"] - b["foreign_sell"]
        trust_net = b["trust_buy"] - b["trust_sell"]
        dealer_net = b["dealer_buy"] - b["dealer_sell"]
        results.append(
            InstitutionalDayRecord(
                date=date_str,
                foreign_buy=b["foreign_buy"],
                foreign_sell=b["foreign_sell"],
                foreign_net=foreign_net,
                trust_buy=b["trust_buy"],
                trust_sell=b["trust_sell"],
                trust_net=trust_net,
                dealer_buy=b["dealer_buy"],
                dealer_sell=b["dealer_sell"],
                dealer_net=dealer_net,
                total_net=foreign_net + trust_net + dealer_net,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("/{symbol}", response_model=InstitutionalResponse)
async def get_institutional(
    symbol: str,
    start_date: str = Query(..., description="ISO start date, e.g. 2026-04-01"),
    end_date: str = Query(..., description="ISO end date, e.g. 2026-04-25"),
) -> InstitutionalResponse:
    """Fetch institutional investor buy/sell data for a TW stock."""
    provider = FinMindInstitutionalProvider()
    try:
        raw = await provider.fetch_institutional(
            stock_id=symbol.replace(".TW", "").replace(".TWO", ""),
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"FinMind error: {exc}") from exc

    if not raw:
        return InstitutionalResponse(symbol=symbol, data=[])

    return InstitutionalResponse(symbol=symbol, data=_aggregate(raw))
