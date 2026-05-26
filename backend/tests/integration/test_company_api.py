"""Integration tests for /api/v1/company/* endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Market
from app.models.industry import Industry
from app.models.stock import Stock

# ── GET /company/{symbol} ─────────────────────────────────────────────────


async def test_get_company_unknown_symbol_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/company/UNKNOWN")
    assert resp.status_code == 404


async def test_get_company_without_industry(client: AsyncClient, db_session: AsyncSession) -> None:
    """Stock with no industry_id → response has industry=''."""
    s = Stock(symbol="2330", name="TSMC", market=Market.TW_TWSE)
    db_session.add(s)
    await db_session.commit()

    resp = await client.get("/api/v1/company/2330")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "2330"
    assert data["name"] == "TSMC"
    assert data["market"] == "TW_TWSE"
    assert data["industry"] == ""


async def test_get_company_with_industry(client: AsyncClient, db_session: AsyncSession) -> None:
    """Stock with industry_id → response includes joined industry name."""
    ind = Industry(name="Semiconductor")
    db_session.add(ind)
    await db_session.commit()
    await db_session.refresh(ind)

    s = Stock(symbol="2330", name="TSMC", market=Market.TW_TWSE)
    s.industry_id = ind.id
    db_session.add(s)
    await db_session.commit()

    resp = await client.get("/api/v1/company/2330")
    assert resp.status_code == 200
    assert resp.json()["industry"] == "Semiconductor"


# ── POST /company/update-info ─────────────────────────────────────────────


async def test_update_info_creates_industry_and_updates_stock(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Mock provider returns a few companies; verify Industry rows are
    created and Stock.industry_id + name get updated."""
    # Seed two stocks (one matches, one doesn't)
    db_session.add(Stock(symbol="2330", name="OldName", market=Market.TW_TWSE))
    db_session.add(Stock(symbol="0050", name="Yuanta", market=Market.TW_TWSE))
    await db_session.commit()

    fake_companies = [
        type(
            "Co",
            (),
            {
                "symbol": "2330",
                "short_name": "TSMC",
                "industry_name": "Semiconductor",
            },
        )(),
        # 9999 doesn't exist in Stock — skipped
        type(
            "Co",
            (),
            {
                "symbol": "9999",
                "short_name": "Phantom",
                "industry_name": "Ghost",
            },
        )(),
    ]

    with patch("app.api.v1.company.TWSECompanyProvider") as prov_cls:
        prov_cls.return_value.fetch_all_companies = AsyncMock(return_value=fake_companies)
        resp = await client.post("/api/v1/company/update-info")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_companies"] == 2
    assert data["updated"] == 1  # only 2330 matched


async def test_update_info_reuses_existing_industry(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """When the Industry row already exists, update_info shouldn't insert
    a duplicate."""
    semi = Industry(name="Semiconductor")
    db_session.add(semi)
    await db_session.commit()
    await db_session.refresh(semi)
    semi_id = semi.id

    db_session.add(Stock(symbol="2330", name="OldName", market=Market.TW_TWSE))
    db_session.add(Stock(symbol="2454", name="OldName2", market=Market.TW_TWSE))
    await db_session.commit()

    fake_companies = [
        type(
            "Co",
            (),
            {
                "symbol": "2330",
                "short_name": "TSMC",
                "industry_name": "Semiconductor",
            },
        )(),
        type(
            "Co",
            (),
            {
                "symbol": "2454",
                "short_name": "MediaTek",
                "industry_name": "Semiconductor",
            },
        )(),
    ]

    with patch("app.api.v1.company.TWSECompanyProvider") as prov_cls:
        prov_cls.return_value.fetch_all_companies = AsyncMock(return_value=fake_companies)
        resp = await client.post("/api/v1/company/update-info")

    assert resp.status_code == 200
    assert resp.json()["updated"] == 2
    # Both stocks point at the existing Industry row (no new row created)
    from sqlalchemy import select

    rows = (await db_session.execute(select(Industry))).scalars().all()
    semi_rows = [r for r in rows if r.name == "Semiconductor"]
    assert len(semi_rows) == 1
    assert semi_rows[0].id == semi_id
