"""Integration tests for /api/v1/signals/recent (pre-market signal board)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from app.models.signal_fire import SignalFire
from app.models.stock import Stock

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession


async def _seed_fires(db: AsyncSession) -> None:
    """Seed three BUY fires from the last hour + one stale fire (>24h)."""
    from app.models.enums import Market

    stock = Stock(symbol="2330", name="台積電", market=Market.TW_TWSE)
    db.add(stock)
    await db.commit()
    await db.refresh(stock)

    now = datetime.now(tz=UTC)
    fresh_a = SignalFire(
        symbol="2330",
        name="台積電",
        signal_type="ma_crossover",
        action="BUY",
        strength=0.8,
        fire_price=Decimal("1245"),
    )
    fresh_b = SignalFire(
        symbol="2454",
        name="聯發科",
        signal_type="rsi_oversold",
        action="BUY",
        strength=0.6,
        fire_price=Decimal("1300"),
    )
    fresh_c = SignalFire(
        symbol="2317",
        name="鴻海",
        signal_type="ma_crossover",
        action="BUY",
        strength=0.7,
        fire_price=Decimal("142"),
    )
    stale = SignalFire(
        symbol="2330",
        name="台積電",
        signal_type="ma_crossover",
        action="BUY",
        strength=0.5,
        fire_price=Decimal("1200"),
    )
    sell_signal = SignalFire(
        symbol="2603",
        name="長榮",
        signal_type="ma_crossover",
        action="SELL",
        strength=0.4,
        fire_price=Decimal("165"),
    )
    db.add_all([fresh_a, fresh_b, fresh_c, stale, sell_signal])
    await db.commit()

    # Backdate the stale fire to >24h ago. Use update because fired_at
    # is init=False (server_default driven).
    from sqlalchemy import update

    await db.execute(
        update(SignalFire)
        .where(SignalFire.id == stale.id)
        .values(fired_at=now - timedelta(hours=48))
    )
    await db.commit()


async def test_recent_empty_db(client: AsyncClient) -> None:
    """Empty DB returns clean empty payload, no 500."""
    resp = await client.get("/api/v1/signals/recent?lookback_hours=20&top=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["signals"] == []
    assert body["grouped"] == {}


async def test_recent_returns_only_buy_within_window(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _seed_fires(db_session)

    resp = await client.get("/api/v1/signals/recent?lookback_hours=20&top=10")
    assert resp.status_code == 200
    body = resp.json()
    symbols = [s["symbol"] for s in body["signals"]]
    # SELL signal excluded; stale ma_crossover dedupes against fresh ma_crossover.
    assert "2603" not in symbols
    # Three unique (symbol, signal_type) fires in window.
    assert len(body["signals"]) == 3


async def test_recent_grouped_counts(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _seed_fires(db_session)

    resp = await client.get("/api/v1/signals/recent?lookback_hours=20&top=10")
    body = resp.json()
    # ma_crossover -> "golden_cross", rsi_oversold -> "rsi_oversold_bounce".
    grouped = body["grouped"]
    assert grouped.get("golden_cross") == 2  # 2330 + 2317
    assert grouped.get("rsi_oversold_bounce") == 1  # 2454


async def test_recent_signal_type_normalized_to_tile_name(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _seed_fires(db_session)

    resp = await client.get("/api/v1/signals/recent?lookback_hours=20&top=10")
    types = {s["signal_type"] for s in resp.json()["signals"]}
    # Raw registry keys must NOT leak through.
    assert "ma_crossover" not in types
    assert "rsi_oversold" not in types
    assert "golden_cross" in types
    assert "rsi_oversold_bounce" in types


async def test_recent_lookback_filters_old_fires(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _seed_fires(db_session)

    # Make the window smaller than the stale (48h) fire's age — still
    # bigger than the fresh fires' age so they remain in the result.
    resp = await client.get("/api/v1/signals/recent?lookback_hours=2&top=10")
    body = resp.json()
    # 3 fresh fires (2330, 2454, 2317); stale 2330 dropped.
    assert len(body["signals"]) == 3
