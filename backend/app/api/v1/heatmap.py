"""Market heatmap API: sector-aggregated performance data."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.industry import Industry
from app.models.price import StockPrice
from app.models.stock import Stock
from app.schemas.market import HeatmapResponse, HeatmapSector, HeatmapStock

MIN_HEATMAP_SECTORS = 5

DbSession = Annotated[AsyncSession, Depends(get_db)]

router = APIRouter(prefix="/heatmap", tags=["heatmap"])


def _demo_heatmap() -> HeatmapResponse:
    """Fallback heatmap data when DB has insufficient sector data."""
    today = str(datetime.now(tz=ZoneInfo("Asia/Taipei")).date())

    sectors_data = [
        (
            "半導體 Semiconductor",
            12,
            1.85,
            125000000,
            [
                ("2330", "台積電 TSMC", 895.0, 4.07, 45230000),
                ("2454", "聯發科 MediaTek", 1285.0, 3.63, 12340000),
                ("2303", "聯電 UMC", 52.3, 2.75, 32100000),
                ("3034", "聯詠 Novatek", 525.0, 2.94, 6780000),
                ("3711", "日月光投控", 158.0, 2.60, 9870000),
            ],
        ),
        (
            "電子零組件 Components",
            15,
            0.62,
            89000000,
            [
                ("2317", "鴻海 Foxconn", 142.0, -3.73, 28900000),
                ("2382", "廣達 Quanta", 312.0, 3.14, 18760000),
                ("3037", "欣興", 178.0, -2.47, 7650000),
                ("2308", "台達電 Delta", 385.0, 1.25, 5430000),
                ("2327", "國巨", 528.0, 0.95, 3210000),
            ],
        ),
        (
            "金融保險 Finance",
            18,
            -0.45,
            98000000,
            [
                ("2881", "富邦金 Fubon", 85.6, 2.64, 15670000),
                ("2891", "中信金", 28.9, -2.53, 42300000),
                ("2882", "國泰金", 58.3, -0.85, 12340000),
                ("2886", "兆豐金", 42.1, 0.48, 8900000),
                ("2884", "玉山金", 27.5, -1.07, 15600000),
            ],
        ),
        (
            "航運 Shipping",
            8,
            -2.15,
            62000000,
            [
                ("2603", "長榮 Evergreen", 165.0, -3.51, 22100000),
                ("2609", "陽明 Yang Ming", 68.4, -3.25, 19870000),
                ("2615", "萬海", 62.3, -1.85, 11200000),
                ("2618", "長榮航", 35.2, -0.56, 8900000),
            ],
        ),
        (
            "塑膠化工 Petrochemical",
            10,
            -1.32,
            45000000,
            [
                ("1301", "台塑 FPC", 62.8, -3.08, 11230000),
                ("1303", "南亞", 56.7, -2.74, 8900000),
                ("6505", "台塑化", 78.5, 3.02, 8920000),
                ("1326", "台化", 48.9, -1.58, 6780000),
            ],
        ),
        (
            "鋼鐵 Steel",
            7,
            -0.89,
            52000000,
            [
                ("2002", "中鋼 CSC", 25.1, -2.90, 35670000),
                ("2015", "豐興", 72.5, 1.25, 3450000),
                ("9958", "世紀鋼", 125.0, -0.40, 2340000),
            ],
        ),
        (
            "食品 Food",
            9,
            0.35,
            28000000,
            [
                ("1216", "統一", 72.3, -2.03, 6540000),
                ("2912", "統一超", 268.0, -2.19, 3210000),
                ("1210", "大成", 48.5, 1.46, 4560000),
            ],
        ),
        (
            "電信 Telecom",
            5,
            0.78,
            18000000,
            [
                ("2412", "中華電 CHT", 132.5, 2.32, 5430000),
                ("3045", "台灣大", 108.0, 0.47, 4320000),
                ("4904", "遠傳", 82.3, -0.24, 3210000),
            ],
        ),
        (
            "電腦周邊 PC/Peripherals",
            11,
            1.12,
            35000000,
            [
                ("2357", "華碩 ASUS", 520.0, 1.76, 5670000),
                ("2353", "宏碁 Acer", 38.6, 0.78, 8900000),
                ("3231", "緯創", 112.0, 2.30, 7650000),
            ],
        ),
        (
            "生技醫療 Biotech",
            6,
            0.92,
            15000000,
            [
                ("4743", "合一", 285.0, 3.27, 4560000),
                ("6446", "藥華藥", 380.0, -1.05, 3210000),
                ("1760", "寶齡富錦", 125.0, 1.62, 2340000),
            ],
        ),
    ]

    sectors = []
    for name, count, avg_chg, total_vol, stocks_data in sectors_data:
        stocks = [
            HeatmapStock(
                symbol=s[0],
                name=s[1],
                close=s[2],
                change_percent=s[3],
                volume=s[4],
            )
            for s in stocks_data
        ]
        sectors.append(
            HeatmapSector(
                industry=name,
                stock_count=count,
                avg_change_percent=avg_chg,
                total_volume=total_vol,
                stocks=stocks,
            )
        )

    return HeatmapResponse(sectors=sectors, date=today)


@router.get("/sectors")
async def get_heatmap_data(
    db: DbSession,
    market_filter: str | None = Query(None),
    top_n: int = Query(default=5, description="Top N stocks per sector"),
) -> HeatmapResponse:
    """Sector heatmap data: avg change per sector with top movers."""

    # Find latest date
    latest_q = select(func.max(StockPrice.date))
    if market_filter:
        latest_q = latest_q.join(Stock, Stock.id == StockPrice.stock_id).where(
            Stock.market == market_filter
        )
    latest_result = await db.execute(latest_q)
    latest_date = latest_result.scalar()

    if not latest_date:
        return _demo_heatmap()

    # Get all stocks with prices for latest date, grouped by industry
    q = (
        select(
            Industry.name.label("industry_name"),
            Stock.symbol,
            Stock.name,
            StockPrice.close,
            StockPrice.change_percent,
            StockPrice.volume,
        )
        .join(Stock, Stock.id == StockPrice.stock_id)
        .join(Industry, Industry.id == Stock.industry_id, isouter=True)
        .where(StockPrice.date == latest_date)
        .where(Stock.industry_id.isnot(None))
        .where(StockPrice.change_percent.isnot(None))
    )
    if market_filter:
        q = q.where(Stock.market == market_filter)

    result = await db.execute(q)
    rows = result.all()

    # Group by industry
    sector_map: dict[str, list] = {}
    for row in rows:
        industry = row.industry_name or "Other"
        if industry not in sector_map:
            sector_map[industry] = []
        sector_map[industry].append(
            HeatmapStock(
                symbol=row.symbol,
                name=row.name or row.symbol,
                close=float(row.close or 0),
                change_percent=float(row.change_percent or 0),
                volume=int(row.volume or 0),
            )
        )

    # Build sector response
    sectors: list[HeatmapSector] = []
    for industry, stocks in sector_map.items():
        avg_change = sum(s.change_percent for s in stocks) / len(stocks) if stocks else 0
        total_vol = sum(s.volume for s in stocks)
        # Sort stocks by absolute change_percent desc, take top N
        sorted_stocks = sorted(stocks, key=lambda s: abs(s.change_percent), reverse=True)[:top_n]

        sectors.append(
            HeatmapSector(
                industry=industry,
                stock_count=len(stocks),
                avg_change_percent=round(avg_change, 2),
                total_volume=total_vol,
                stocks=sorted_stocks,
            )
        )

    # Sort sectors by stock_count desc (largest sectors first)
    sectors.sort(key=lambda s: s.stock_count, reverse=True)

    # Fallback: if DB has fewer than MIN_HEATMAP_SECTORS, supplement with demo data
    if len(sectors) < MIN_HEATMAP_SECTORS:
        demo = _demo_heatmap()
        existing_industries = {s.industry for s in sectors}
        for demo_sector in demo.sectors:
            if demo_sector.industry not in existing_industries:
                sectors.append(demo_sector)
                existing_industries.add(demo_sector.industry)

    return HeatmapResponse(sectors=sectors, date=str(latest_date))
