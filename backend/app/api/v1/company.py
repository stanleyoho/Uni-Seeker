from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.api.deps import get_db
from app.models.stock import Stock
from app.modules.company.twse_company import TWSECompanyProvider

router = APIRouter(prefix="/company", tags=["company"])


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
            stock.industry = company.industry_name
            stock.name = company.short_name
            updated += 1

    await db.commit()
    return {"total_companies": len(companies), "updated": updated}
