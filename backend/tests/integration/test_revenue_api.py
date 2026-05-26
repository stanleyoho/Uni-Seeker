"""Integration tests for /api/v1/revenue/* endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Market
from app.models.revenue import MonthlyRevenue
from app.models.stock import Stock
from app.modules.revenue.base import RevenueRecord


def _rec(
    symbol: str = "2330",
    period: str = "2026-Q1",
    revenue: float = 1_000_000.0,
    mom_growth: float | None = None,
    yoy_growth: float | None = None,
) -> RevenueRecord:
    return RevenueRecord(
        symbol=symbol,
        period=period,
        period_type="quarterly",
        revenue=revenue,
        currency="TWD",
        mom_growth=mom_growth,
        yoy_growth=yoy_growth,
    )


# ── GET /revenue/{symbol} ─────────────────────────────────────────────────


async def test_get_revenue_no_records_404(client: AsyncClient) -> None:
    """Provider returns no records → 404."""
    with patch("app.api.v1.revenue.YFinanceRevenueProvider") as prov_cls:
        prov_cls.return_value.fetch_revenue = AsyncMock(return_value=[])
        resp = await client.get("/api/v1/revenue/UNKNOWN")
    assert resp.status_code == 404


async def test_get_revenue_unanalyzable_404(client: AsyncClient) -> None:
    """analyze_revenue returns None (e.g. insufficient periods) → 404."""
    with (
        patch("app.api.v1.revenue.YFinanceRevenueProvider") as prov_cls,
        patch("app.api.v1.revenue.analyze_revenue", return_value=None),
    ):
        prov_cls.return_value.fetch_revenue = AsyncMock(return_value=[_rec()])
        resp = await client.get("/api/v1/revenue/2330")
    assert resp.status_code == 404


async def test_get_revenue_happy_path(client: AsyncClient) -> None:
    """Multi-quarter records → 200 with full analysis payload."""
    records = [
        _rec(period=f"2026-Q{q}", revenue=1_000_000 + q * 100_000) for q in range(1, 5)
    ]
    with patch("app.api.v1.revenue.YFinanceRevenueProvider") as prov_cls:
        prov_cls.return_value.fetch_revenue = AsyncMock(return_value=records)
        resp = await client.get("/api/v1/revenue/2330")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "2330"
    assert "latest_revenue" in data
    assert "trend" in data
    assert len(data["records"]) == 4


# ── POST /revenue/update-tw ───────────────────────────────────────────────


async def test_update_tw_no_matching_stocks_stored_zero(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Provider returns records but no Stock rows match → stored=0."""
    fake = [_rec(symbol="9999", period="2026-01")]
    with patch("app.api.v1.revenue.TWSERevenueProvider") as prov_cls:
        prov_cls.return_value.fetch_all_revenue = AsyncMock(return_value=fake)
        resp = await client.post("/api/v1/revenue/update-tw")
    assert resp.status_code == 200
    data = resp.json()
    assert data["fetched"] == 1
    assert data["stored"] == 0


async def test_update_tw_persists_new_record(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Stock exists + new period → persisted (stored=1)."""
    db_session.add(Stock(symbol="2330", name="TSMC", market=Market.TW_TWSE))
    await db_session.commit()

    fake = [_rec(symbol="2330", period="2026-04", revenue=1_500_000, mom_growth=2.5, yoy_growth=10.0)]
    with patch("app.api.v1.revenue.TWSERevenueProvider") as prov_cls:
        prov_cls.return_value.fetch_all_revenue = AsyncMock(return_value=fake)
        resp = await client.post("/api/v1/revenue/update-tw")
    assert resp.status_code == 200
    assert resp.json()["stored"] == 1

    # Verify row in DB
    from sqlalchemy import select
    rows = (await db_session.execute(select(MonthlyRevenue))).scalars().all()
    assert len(rows) == 1
    assert float(rows[0].revenue) == 1_500_000.0


async def test_update_tw_skips_existing_period(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """If MonthlyRevenue already exists for stock_id + period → skip."""
    from decimal import Decimal
    s = Stock(symbol="2330", name="TSMC", market=Market.TW_TWSE)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    db_session.add(
        MonthlyRevenue(
            stock_id=s.id,
            period="2026-04",
            revenue=Decimal("1000000"),
            currency="TWD",
        )
    )
    await db_session.commit()

    fake = [_rec(symbol="2330", period="2026-04")]
    with patch("app.api.v1.revenue.TWSERevenueProvider") as prov_cls:
        prov_cls.return_value.fetch_all_revenue = AsyncMock(return_value=fake)
        resp = await client.post("/api/v1/revenue/update-tw")
    assert resp.status_code == 200
    assert resp.json()["stored"] == 0  # Duplicate skipped


async def test_update_tw_handles_null_growth_fields(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """mom_growth/yoy_growth = None → stored as NULL not crash."""
    db_session.add(Stock(symbol="2330", name="TSMC", market=Market.TW_TWSE))
    await db_session.commit()

    fake = [_rec(symbol="2330", period="2026-04", mom_growth=None, yoy_growth=None)]
    with patch("app.api.v1.revenue.TWSERevenueProvider") as prov_cls:
        prov_cls.return_value.fetch_all_revenue = AsyncMock(return_value=fake)
        resp = await client.post("/api/v1/revenue/update-tw")
    assert resp.status_code == 200
    assert resp.json()["stored"] == 1

    from sqlalchemy import select
    row = (await db_session.execute(select(MonthlyRevenue))).scalar_one()
    assert row.mom_growth is None
    assert row.yoy_growth is None
