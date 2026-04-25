from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.api.deps import get_db, get_stock_or_404
from app.models.industry import Industry
from app.models.stock import Stock
from app.modules.company.twse_company import TWSECompanyProvider

router = APIRouter(prefix="/company", tags=["company"])


class StockInfoResponse(BaseModel):
    symbol: str
    name: str
    market: str
    industry: str


@router.get("/{symbol}", response_model=StockInfoResponse)
async def get_company_info(
    symbol: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StockInfoResponse:
    """Get company info for a single stock."""
    stock = await get_stock_or_404(db, symbol)

    # Resolve industry name via JOIN
    industry_name = ""
    if stock.industry_id is not None:
        ind_result = await db.execute(
            select(Industry.name).where(Industry.id == stock.industry_id)
        )
        ind_row = ind_result.scalar_one_or_none()
        if ind_row:
            industry_name = ind_row

    return StockInfoResponse(
        symbol=stock.symbol,
        name=stock.name or "",
        market=stock.market.value if stock.market else "",
        industry=industry_name,
    )


@router.post("/update-info")
async def update_company_info(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Fetch TWSE company data and update Stock table industry field."""
    async with httpx.AsyncClient(timeout=60, verify=False) as client:
        provider = TWSECompanyProvider(client=client)
        companies = await provider.fetch_all_companies()

    updated = 0
    for company in companies:
        result = await db.execute(
            select(Stock).where(Stock.symbol == company.symbol)
        )
        stock = result.scalar_one_or_none()
        if stock:
            # Find or create the industry
            ind_result = await db.execute(
                select(Industry).where(Industry.name == company.industry_name)
            )
            industry = ind_result.scalar_one_or_none()
            if not industry:
                industry = Industry(name=company.industry_name)
                db.add(industry)
                await db.flush()

            stock.industry_id = industry.id
            stock.name = company.short_name
            updated += 1

    await db.commit()
    return {"total_companies": len(companies), "updated": updated}
