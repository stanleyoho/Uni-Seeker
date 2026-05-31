#!/usr/bin/env python3
"""E2E test seed — provisions a deterministic dataset for the Playwright suite.

This script is the bootstrap step in `docker-compose.e2e.yml`: it runs once
after Postgres is healthy and before backend / frontend start. The same
script is safe to invoke ad-hoc against an existing DB for local re-runs.

Idempotency contract
--------------------
Every insert is wrapped in an "exists? skip : create" guard so re-running
the script against a partially-seeded DB does NOT explode on UNIQUE
constraint violations. The schema is built on first run via
``Base.metadata.create_all`` (mirroring the pg_integration conftest path —
see backend/tests/conftest.py for the alembic-baseline-workaround
context). PG enum types that models declare with ``create_type=False`` are
created manually before the table create.

What gets seeded
----------------
1. User: ``e2e@example.com`` / ``e2e-test-pw`` (Pro tier)
2. Industry: Semiconductors (id used by stocks below)
3. Stocks: 2330 / 台積電 (TW_TWSE), 2317 / 鴻海 (TW_TWSE), AAPL / Apple Inc. (US_NASDAQ)
4. Stock prices: ~60 daily rows per stock (enough to clear
   ``MIN_DATA_POINTS = 20`` and produce non-trivial backtest metrics)
5. Watchlist: one item for the e2e user (so /portfolio renders content)
6. Portfolio account + one BUY trade on 2330 with companion lot + position
   rows (so /holdings KPIs are non-zero and the positions table renders)
7. F13Filer: Berkshire Hathaway (CIK 0001067983) + e2e user subscription
   + one F13 filing + one F13 holding (so /institutional renders content)

Specs that depend on this seed: see ``frontend/e2e/*.spec.ts``.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

# Allow running both as a module (in container) and as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Import every model module that backend code relies on so SQLAlchemy
# sees the full metadata before create_all. `app.models` is the legacy
# flat-namespace package (User, Stock, StockPrice, WatchlistItem,
# Industry, …). `app.db.models` is the newer hierarchical layout
# (PortfolioAccount, F13Filer, alerts, …). Both packages' __init__.py
# do eager imports of their submodules.
import app.db.models  # registers F13 / portfolio / alerts models
import app.models  # noqa: F401 — registers legacy flat-namespace models (side-effect only)
from app.auth import hash_password
from app.db.models.institutional.filer import F13Filer
from app.db.models.institutional.filing import F13Filing
from app.db.models.institutional.holding import F13Holding
from app.db.models.institutional.subscription import F13UserSubscription
from app.db.models.portfolio.account import PortfolioAccount
from app.db.models.portfolio.lot import PortfolioLot
from app.db.models.portfolio.position import PortfolioPosition
from app.db.models.portfolio.trade import PortfolioTrade
from app.models.base import Base
from app.models.enums import Market, UserTier
from app.models.industry import Industry
from app.models.price import StockPrice
from app.models.stock import Stock
from app.models.user import User
from app.models.watchlist_item import WatchlistItem

E2E_EMAIL = "e2e@example.com"
E2E_PASSWORD = "e2e-test-pw"
E2E_USERNAME = "e2etest"

# Berkshire's CIK is well-known and the smoke-e2e script uses the same
# value — keep them in lockstep so any change here mirrors there.
BERKSHIRE_CIK = "0001067983"
BERKSHIRE_NAME = "BERKSHIRE HATHAWAY INC"


def _create_pg_enums(connection) -> None:
    """Create PG enums up-front because models use ``create_type=False``.

    Mirrors ``backend/tests/conftest.py::_create_pg_enums_sync``. Wrapped
    in IF NOT EXISTS guards so re-runs against an already-seeded DB
    don't blow up.
    """
    connection.execute(
        text(
            "DO $$ BEGIN "
            "CREATE TYPE market_enum AS ENUM ('TW_TWSE','TW_TPEX','US_NYSE','US_NASDAQ'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        )
    )
    connection.execute(
        text(
            "DO $$ BEGIN "
            "CREATE TYPE user_tier_enum AS ENUM ('free','basic','pro'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        )
    )
    connection.execute(
        text(
            "DO $$ BEGIN "
            "CREATE TYPE notification_status_enum AS ENUM ('pending','success','failed'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        )
    )


def _build_schema(connection) -> None:
    Base.metadata.create_all(connection)


async def _ensure_user(session) -> User:
    existing = (
        await session.execute(select(User).where(User.email == E2E_EMAIL))
    ).scalar_one_or_none()
    if existing is not None:
        # Force Pro tier in case a previous run left it as FREE.
        if existing.tier != UserTier.PRO:
            existing.tier = UserTier.PRO
            await session.flush()
        print(f"[seed] user already exists id={existing.id}")
        return existing

    user = User(
        email=E2E_EMAIL,
        hashed_password=hash_password(E2E_PASSWORD),
        username=E2E_USERNAME,
        tier=UserTier.PRO,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    print(f"[seed] created user id={user.id}")
    return user


async def _ensure_industry(session) -> Industry:
    existing = (
        await session.execute(select(Industry).where(Industry.name == "Semiconductors"))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    industry = Industry(name="Semiconductors")
    session.add(industry)
    await session.flush()
    print(f"[seed] created industry id={industry.id}")
    return industry


async def _ensure_stock(
    session, *, symbol: str, name: str, market: Market, industry_id: int | None
) -> Stock:
    existing = (
        await session.execute(select(Stock).where(Stock.symbol == symbol))
    ).scalar_one_or_none()
    if existing is not None:
        # Heal a previous broken seed where name might have been empty —
        # the /stocks/[symbol] regression Stanley flagged.
        if existing.name != name and name:
            existing.name = name
            await session.flush()
        return existing
    stock = Stock(symbol=symbol, name=name, market=market, industry_id=industry_id)
    session.add(stock)
    await session.flush()
    print(f"[seed] created stock {symbol} id={stock.id}")
    return stock


async def _ensure_prices(session, *, stock: Stock, days: int, base_price: float) -> None:
    """Generate `days` daily price rows ending today, deterministic."""
    existing_count = (
        (await session.execute(select(StockPrice).where(StockPrice.stock_id == stock.id)))
        .scalars()
        .all()
    )
    if len(existing_count) >= days:
        return

    today = date.today()
    rows: list[StockPrice] = []
    # Simple deterministic walk so backtester sees non-flat data — needed
    # for rsi_oversold to produce trades.
    for i in range(days):
        d = today - timedelta(days=days - i)
        # Sine-like oscillation around base_price so RSI swings cross 30/70.
        offset = (i % 10) - 5
        close = Decimal(str(round(base_price + offset * (base_price * 0.01), 2)))
        open_ = close - Decimal("1.00")
        high = close + Decimal("2.00")
        low = close - Decimal("2.00")
        rows.append(
            StockPrice(
                stock_id=stock.id,
                date=d,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=1_000_000 + i * 1000,
            )
        )
    session.add_all(rows)
    await session.flush()
    print(f"[seed] created {len(rows)} prices for {stock.symbol}")


async def _ensure_watchlist(session, *, user: User, stock: Stock) -> None:
    existing = (
        await session.execute(
            select(WatchlistItem).where(
                WatchlistItem.user_id == user.id,
                WatchlistItem.stock_id == stock.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    item = WatchlistItem(user_id=user.id, stock_id=stock.id)
    session.add(item)
    await session.flush()
    print(f"[seed] created watchlist item for {stock.symbol}")


async def _ensure_portfolio_account(session, *, user: User) -> PortfolioAccount:
    existing = (
        await session.execute(
            select(PortfolioAccount).where(
                PortfolioAccount.user_id == user.id,
                PortfolioAccount.name == "E2E 永豐",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    account = PortfolioAccount(
        user_id=user.id,
        name="E2E 永豐",
        market=Market.TW_TWSE,
        currency="TWD",
        broker="SinoPac",
        description="E2E test account",
    )
    session.add(account)
    await session.flush()
    print(f"[seed] created portfolio account id={account.id}")
    return account


async def _ensure_trade(session, *, account: PortfolioAccount, symbol: str) -> None:
    """Insert the seed BUY trade AND materialize its lot + position rows.

    Production trade ingestion goes through `PortfolioTradeService.record_trade`
    which (1) writes the trade, (2) opens a `PortfolioLot` via `apply_buy`,
    and (3) re-derives the `PortfolioPosition` roll-up. The /holdings page
    reads from `portfolio_positions`, NOT `portfolio_trades`, so a trade
    inserted without its companion lot/position rows renders the page as
    empty ("無持倉"). The seed mirrors the service's BUY path manually
    instead of importing the service (which would require User/session
    plumbing not appropriate inside the seed).

    For BUY qty=1000 @ price=580 fee=0:
      lot.cost_per_unit  = 580
      lot.original_qty   = lot.remaining_qty = 1000
      position.quantity  = 1000
      position.avg_cost  = 580
      position.total_cost = 580 * 1000 = 580_000
    """
    qty = Decimal("1000")
    price = Decimal("580.00")

    trade = (
        await session.execute(
            select(PortfolioTrade).where(
                PortfolioTrade.account_id == account.id,
                PortfolioTrade.symbol == symbol,
            )
        )
    ).scalar_one_or_none()
    if trade is None:
        trade = PortfolioTrade(
            account_id=account.id,
            symbol=symbol,
            market=Market.TW_TWSE,
            action="BUY",
            trade_date=date.today() - timedelta(days=10),
            price=price,
            quantity=qty,
        )
        session.add(trade)
        await session.flush()
        print(f"[seed] created trade for {symbol} on account {account.id}")

    # Lot / position are companion rows for this trade. Guard each
    # independently so a partially-seeded DB heals on re-run instead of
    # silently leaving /holdings empty.
    existing_lot = (
        await session.execute(select(PortfolioLot).where(PortfolioLot.trade_id == trade.id))
    ).scalar_one_or_none()
    if existing_lot is None:
        lot = PortfolioLot(
            trade_id=trade.id,
            account_id=account.id,
            symbol=symbol,
            market=Market.TW_TWSE,
            original_qty=qty,
            remaining_qty=qty,
            cost_per_unit=price,
        )
        session.add(lot)
        await session.flush()
        print(f"[seed] created lot id={lot.id} for trade {trade.id}")

    existing_position = (
        await session.execute(
            select(PortfolioPosition).where(
                PortfolioPosition.account_id == account.id,
                PortfolioPosition.symbol == symbol,
                PortfolioPosition.market == Market.TW_TWSE,
            )
        )
    ).scalar_one_or_none()
    if existing_position is None:
        total_cost = price * qty
        position = PortfolioPosition(
            account_id=account.id,
            symbol=symbol,
            market=Market.TW_TWSE,
            currency=account.currency,
            quantity=qty,
            avg_cost_fifo=price,
            total_cost=total_cost,
        )
        session.add(position)
        await session.flush()
        print(f"[seed] created position id={position.id} qty={qty} cost={total_cost}")


async def _ensure_filer_and_subscription(session, *, user: User) -> F13Filer:
    filer = (
        await session.execute(select(F13Filer).where(F13Filer.cik == BERKSHIRE_CIK))
    ).scalar_one_or_none()
    if filer is None:
        filer = F13Filer(
            cik=BERKSHIRE_CIK,
            name=BERKSHIRE_NAME,
            latest_total_value_usd=Decimal("300000000000"),
            latest_filing_date=date.today() - timedelta(days=30),
            latest_position_count=50,
        )
        session.add(filer)
        await session.flush()
        print(f"[seed] created filer id={filer.id}")

    sub = (
        await session.execute(
            select(F13UserSubscription).where(
                F13UserSubscription.user_id == user.id,
                F13UserSubscription.filer_id == filer.id,
            )
        )
    ).scalar_one_or_none()
    if sub is None:
        sub = F13UserSubscription(user_id=user.id, filer_id=filer.id)
        session.add(sub)
        await session.flush()
        print(f"[seed] created subscription user={user.id} filer={filer.id}")
    return filer


async def _ensure_filing_and_holding(session, *, filer: F13Filer) -> None:
    filing = (
        await session.execute(select(F13Filing).where(F13Filing.filer_id == filer.id))
    ).scalar_one_or_none()
    if filing is None:
        # report_period_end matches what the dashboard expects to show.
        report_period_end = date.today() - timedelta(days=60)
        filing = F13Filing(
            filer_id=filer.id,
            accession_number=f"e2e-seed-{filer.id}-0001",
            form_type="13F-HR",
            report_period_end=report_period_end,
            filed_at=datetime.combine(date.today() - timedelta(days=30), datetime.min.time()),
        )
        session.add(filing)
        await session.flush()
        print(f"[seed] created filing id={filing.id}")

    holding = (
        await session.execute(select(F13Holding).where(F13Holding.filing_id == filing.id))
    ).scalar_one_or_none()
    if holding is None:
        holding = F13Holding(
            filing_id=filing.id,
            cusip="037833100",
            name_of_issuer="APPLE INC",
            value_usd=Decimal("1100000000"),
            shares=Decimal("5500000"),
        )
        session.add(holding)
        await session.flush()
        print(f"[seed] created holding for filing {filing.id}")


async def main() -> int:
    db_url = os.environ.get(
        "UNI_DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5434/uni_seeker_e2e",
    )
    print(f"[seed] target db={db_url.split('@')[-1]}")

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(_create_pg_enums)
        await conn.run_sync(_build_schema)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        user = await _ensure_user(session)
        industry = await _ensure_industry(session)

        tsmc = await _ensure_stock(
            session,
            symbol="2330",
            name="台積電",
            market=Market.TW_TWSE,
            industry_id=industry.id,
        )
        await _ensure_stock(
            session,
            symbol="2317",
            name="鴻海",
            market=Market.TW_TWSE,
            industry_id=industry.id,
        )
        await _ensure_stock(
            session,
            symbol="AAPL",
            name="Apple Inc.",
            market=Market.US_NASDAQ,
            industry_id=None,
        )

        # Enough rows for rsi_oversold to fire (MIN_DATA_POINTS=20).
        await _ensure_prices(session, stock=tsmc, days=60, base_price=600.0)

        await _ensure_watchlist(session, user=user, stock=tsmc)

        account = await _ensure_portfolio_account(session, user=user)
        await _ensure_trade(session, account=account, symbol="2330")

        filer = await _ensure_filer_and_subscription(session, user=user)
        await _ensure_filing_and_holding(session, filer=filer)

        await session.commit()

    await engine.dispose()
    print("[seed] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
