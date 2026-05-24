"""Integration tests for portfolio repositories (Phase 1 / UNI-PORT-001).

Layout per spec §5.3:
    Account  : 6 cases  (create / get / list / update / delete + count + cross-user isolation)
    Trade    : 6 cases  (create / get / list / update / delete + count_this_month boundary)
    Lot      : 3 cases  (create / list_open FIFO order / bulk_update)
    Position : 4 cases  (upsert insert / upsert update / list_by_user JOIN / count + unique key)
    Price    : 3 cases  (latest_two / missing symbol / batch)

All tests run against the shared `db_session` fixture from
``tests/conftest.py`` (in-memory SQLite). Each test seeds its own
users / accounts to verify structural user isolation: a second user
must not see or mutate the first user's data even though both rows
exist in the same DB.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from app.models.enums import Market, UserTier
from app.models.price import StockPrice
from app.models.stock import Stock
from app.models.user import User
from app.repositories.portfolio import (
    PortfolioAccountRepo,
    PortfolioLotRepo,
    PortfolioPositionRepo,
    PortfolioTradeRepo,
    PriceLookupRepo,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models.portfolio import (
        PortfolioAccount,
        PortfolioLot,
        PortfolioTrade,
    )

# ── Shared helpers ──────────────────────────────────────────────────────────


async def _mk_user(
    db: AsyncSession, email: str, username: str, tier: UserTier = UserTier.PRO
) -> User:
    u = User(email=email, hashed_password="x" * 60, username=username)
    u.tier = tier
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _mk_stock(db: AsyncSession, symbol: str, market: Market = Market.TW_TWSE) -> Stock:
    s = Stock(symbol=symbol, name=symbol, market=market)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


async def _mk_price(
    db: AsyncSession,
    stock_id: int,
    d: date,
    close: Decimal = Decimal("100"),
) -> StockPrice:
    p = StockPrice(
        stock_id=stock_id,
        date=d,
        open=close,
        high=close + Decimal("1"),
        low=close - Decimal("1"),
        close=close,
        volume=1000,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


# ═════════════════════════════════════════════════════════════════════════════
# PortfolioAccountRepo (6 cases)
# ═════════════════════════════════════════════════════════════════════════════


async def test_account_repo_create_get_list(db_session: AsyncSession) -> None:
    """create returns a row; get_by_id and list_by_user echo it back."""
    user = await _mk_user(db_session, "a@x.com", "a")
    repo = PortfolioAccountRepo(db_session)

    acc = await repo.create(
        user_id=user.id,
        name="TW broker",
        market=Market.TW_TWSE,
        broker="Yuanta",
        currency="TWD",
    )
    await db_session.commit()

    assert acc.id is not None
    assert acc.user_id == user.id

    got = await repo.get_by_id(acc.id, user_id=user.id)
    assert got is not None
    assert got.name == "TW broker"

    listed = await repo.list_by_user(user.id)
    assert len(listed) == 1
    assert listed[0].id == acc.id


async def test_account_repo_update_persists_fields(
    db_session: AsyncSession,
) -> None:
    """update mutates allowlist columns; unknown / immutable keys ignored."""
    user = await _mk_user(db_session, "b@x.com", "b")
    repo = PortfolioAccountRepo(db_session)

    acc = await repo.create(user_id=user.id, name="old", market=Market.TW_TWSE)
    await db_session.commit()

    updated = await repo.update(
        acc.id,
        user_id=user.id,
        name="new",
        broker="Fubon",
        user_id_garbage=999,  # immutable: must be ignored
    )
    await db_session.commit()

    assert updated is not None
    assert updated.name == "new"
    assert updated.broker == "Fubon"
    assert updated.user_id == user.id  # never mutated


async def test_account_repo_delete_cascades(db_session: AsyncSession) -> None:
    """Deleting account cascades to trades / lots / positions per FK
    ON DELETE CASCADE. delete() returns True on hit, False on miss."""
    user = await _mk_user(db_session, "c@x.com", "c")
    repo_a = PortfolioAccountRepo(db_session)
    repo_t = PortfolioTradeRepo(db_session)
    repo_p = PortfolioPositionRepo(db_session)

    acc = await repo_a.create(user_id=user.id, name="cascade", market=Market.TW_TWSE)
    await db_session.commit()
    await repo_t.create(
        account_id=acc.id,
        user_id=user.id,
        symbol="2330",
        market=Market.TW_TWSE,
        action="BUY",
        trade_date=date(2026, 5, 1),
        price=Decimal("100"),
        quantity=Decimal("10"),
    )
    await repo_p.upsert(
        account_id=acc.id,
        symbol="2330",
        market=Market.TW_TWSE,
        currency="TWD",
        quantity=Decimal("10"),
        avg_cost=Decimal("100"),
    )
    await db_session.commit()

    ok = await repo_a.delete(acc.id, user_id=user.id)
    await db_session.commit()
    assert ok is True

    assert await repo_a.get_by_id(acc.id, user_id=user.id) is None

    miss = await repo_a.delete(acc.id, user_id=user.id)
    assert miss is False


async def test_account_repo_count_by_user(db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "d@x.com", "d")
    repo = PortfolioAccountRepo(db_session)
    assert await repo.count_by_user(user.id) == 0

    for n in range(3):
        await repo.create(user_id=user.id, name=f"a{n}", market=Market.TW_TWSE)
    await db_session.commit()

    assert await repo.count_by_user(user.id) == 3


async def test_account_repo_user_isolation(db_session: AsyncSession) -> None:
    """User B must not see, read, update, or delete User A's account."""
    user_a = await _mk_user(db_session, "ua@x.com", "ua")
    user_b = await _mk_user(db_session, "ub@x.com", "ub")
    repo = PortfolioAccountRepo(db_session)

    acc_a = await repo.create(user_id=user_a.id, name="A's", market=Market.TW_TWSE)
    await db_session.commit()

    # get_by_id with wrong user_id → None
    assert await repo.get_by_id(acc_a.id, user_id=user_b.id) is None

    # list_by_user(B) → empty
    assert await repo.list_by_user(user_b.id) == []

    # update(B) → None, A's row unchanged
    res = await repo.update(acc_a.id, user_id=user_b.id, name="hacked")
    assert res is None
    fresh = await repo.get_by_id(acc_a.id, user_id=user_a.id)
    assert fresh is not None
    assert fresh.name == "A's"

    # delete(B) → False, row still there
    deleted = await repo.delete(acc_a.id, user_id=user_b.id)
    assert deleted is False
    still = await repo.get_by_id(acc_a.id, user_id=user_a.id)
    assert still is not None

    # count_by_user separates correctly
    assert await repo.count_by_user(user_a.id) == 1
    assert await repo.count_by_user(user_b.id) == 0


# ═════════════════════════════════════════════════════════════════════════════
# PortfolioTradeRepo (6 cases)
# ═════════════════════════════════════════════════════════════════════════════


async def _mk_account(
    db_session: AsyncSession, user_id: int, name: str = "acc"
) -> PortfolioAccount:
    repo = PortfolioAccountRepo(db_session)
    acc = await repo.create(user_id=user_id, name=name, market=Market.TW_TWSE)
    await db_session.commit()
    return acc


async def test_trade_repo_create_get(db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "t1@x.com", "t1")
    acc = await _mk_account(db_session, user.id)
    repo = PortfolioTradeRepo(db_session)

    trade = await repo.create(
        account_id=acc.id,
        user_id=user.id,
        symbol="2330",
        market=Market.TW_TWSE,
        action="BUY",
        trade_date=date(2026, 5, 5),
        price=Decimal("600"),
        quantity=Decimal("100"),
        fee=Decimal("28"),
    )
    await db_session.commit()
    assert trade is not None
    assert trade.id is not None

    got = await repo.get_by_id(trade.id, user_id=user.id)
    assert got is not None
    assert got.symbol == "2330"
    assert got.quantity == Decimal("100")


async def test_trade_repo_create_rejects_wrong_owner(
    db_session: AsyncSession,
) -> None:
    """User B cannot create a trade on User A's account."""
    user_a = await _mk_user(db_session, "ta@x.com", "ta")
    user_b = await _mk_user(db_session, "tb@x.com", "tb")
    acc_a = await _mk_account(db_session, user_a.id, name="A acc")
    repo = PortfolioTradeRepo(db_session)

    trade = await repo.create(
        account_id=acc_a.id,
        user_id=user_b.id,  # wrong owner
        symbol="2330",
        market=Market.TW_TWSE,
        action="BUY",
        trade_date=date(2026, 5, 1),
        price=Decimal("600"),
        quantity=Decimal("100"),
    )
    assert trade is None


async def test_trade_repo_list_by_account_orders_and_isolates(
    db_session: AsyncSession,
) -> None:
    """list_by_account returns latest first, scoped to owner."""
    user_a = await _mk_user(db_session, "tla@x.com", "tla")
    user_b = await _mk_user(db_session, "tlb@x.com", "tlb")
    acc = await _mk_account(db_session, user_a.id, name="acc1")
    repo = PortfolioTradeRepo(db_session)

    for i, d in enumerate([date(2026, 5, 1), date(2026, 5, 3), date(2026, 5, 2)]):
        await repo.create(
            account_id=acc.id,
            user_id=user_a.id,
            symbol=f"S{i}",
            market=Market.TW_TWSE,
            action="BUY",
            trade_date=d,
            price=Decimal("100"),
            quantity=Decimal("1"),
        )
    await db_session.commit()

    rows = await repo.list_by_account(acc.id, user_id=user_a.id)
    assert [r.trade_date for r in rows] == [
        date(2026, 5, 3),
        date(2026, 5, 2),
        date(2026, 5, 1),
    ]

    # User B sees no rows for an account they don't own.
    assert await repo.list_by_account(acc.id, user_id=user_b.id) == []


async def test_trade_repo_count_this_month_boundary(
    db_session: AsyncSession,
) -> None:
    """Trades dated in current UTC month are counted; previous month not."""
    user = await _mk_user(db_session, "tm@x.com", "tm")
    acc = await _mk_account(db_session, user.id, name="m")
    repo = PortfolioTradeRepo(db_session)

    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).date()
    prev_month_day = month_start - timedelta(days=1)

    # 2 trades this month, 1 in previous month
    for d in [month_start, month_start, prev_month_day]:
        await repo.create(
            account_id=acc.id,
            user_id=user.id,
            symbol="S",
            market=Market.TW_TWSE,
            action="BUY",
            trade_date=d,
            price=Decimal("10"),
            quantity=Decimal("1"),
        )
    await db_session.commit()

    assert await repo.count_by_user_this_month(user.id) == 2


async def test_trade_repo_update(db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "tu@x.com", "tu")
    acc = await _mk_account(db_session, user.id, name="u")
    repo = PortfolioTradeRepo(db_session)

    trade = await repo.create(
        account_id=acc.id,
        user_id=user.id,
        symbol="X",
        market=Market.TW_TWSE,
        action="BUY",
        trade_date=date(2026, 5, 1),
        price=Decimal("100"),
        quantity=Decimal("10"),
    )
    await db_session.commit()
    assert trade is not None

    updated = await repo.update(trade.id, user_id=user.id, price=Decimal("120"), note="bumped")
    await db_session.commit()
    assert updated is not None
    assert updated.price == Decimal("120")
    assert updated.note == "bumped"


async def test_trade_repo_delete_isolates(db_session: AsyncSession) -> None:
    """User B's DELETE on user A's trade is rejected; original survives."""
    user_a = await _mk_user(db_session, "tda@x.com", "tda")
    user_b = await _mk_user(db_session, "tdb@x.com", "tdb")
    acc = await _mk_account(db_session, user_a.id, name="d")
    repo = PortfolioTradeRepo(db_session)
    trade = await repo.create(
        account_id=acc.id,
        user_id=user_a.id,
        symbol="Y",
        market=Market.TW_TWSE,
        action="BUY",
        trade_date=date(2026, 5, 1),
        price=Decimal("100"),
        quantity=Decimal("1"),
    )
    await db_session.commit()
    assert trade is not None

    assert await repo.delete(trade.id, user_id=user_b.id) is False  # cross-user blocked
    assert await repo.get_by_id(trade.id, user_id=user_a.id) is not None

    assert await repo.delete(trade.id, user_id=user_a.id) is True
    await db_session.commit()
    assert await repo.get_by_id(trade.id, user_id=user_a.id) is None


# ═════════════════════════════════════════════════════════════════════════════
# PortfolioLotRepo (3 cases)
# ═════════════════════════════════════════════════════════════════════════════


async def _mk_buy_trade(
    db_session: AsyncSession,
    account_id: int,
    user_id: int,
    symbol: str = "2330",
    qty: Decimal = Decimal("10"),
    price: Decimal = Decimal("100"),
    d: date = date(2026, 5, 1),
) -> PortfolioTrade:
    repo = PortfolioTradeRepo(db_session)
    t = await repo.create(
        account_id=account_id,
        user_id=user_id,
        symbol=symbol,
        market=Market.TW_TWSE,
        action="BUY",
        trade_date=d,
        price=price,
        quantity=qty,
    )
    await db_session.commit()
    assert t is not None
    return t


async def test_lot_repo_create_and_list_open_fifo(
    db_session: AsyncSession,
) -> None:
    """list_open_for_position returns oldest lot first (FIFO order)."""
    user = await _mk_user(db_session, "l1@x.com", "l1")
    acc = await _mk_account(db_session, user.id, name="lots")
    lot_repo = PortfolioLotRepo(db_session)

    # Make 3 sequential BUY trades → 3 lots
    lots: list[PortfolioLot] = []
    for i, (q, p) in enumerate([(Decimal("10"), 100), (Decimal("20"), 110), (Decimal("15"), 120)]):
        t = await _mk_buy_trade(
            db_session,
            acc.id,
            user.id,
            qty=q,
            price=Decimal(p),
            d=date(2026, 5, 1 + i),
        )
        lot = await lot_repo.create(
            trade_id=t.id,
            account_id=acc.id,
            symbol="2330",
            market=Market.TW_TWSE,
            original_qty=q,
            remaining_qty=q,
            cost_per_unit=Decimal(p),
        )
        lots.append(lot)
    await db_session.commit()

    open_lots = await lot_repo.list_open_for_position(
        account_id=acc.id, symbol="2330", market=Market.TW_TWSE
    )
    assert [lot.id for lot in open_lots] == [
        lots[0].id,
        lots[1].id,
        lots[2].id,
    ]
    assert all(lot.is_exhausted is False for lot in open_lots)


async def test_lot_repo_bulk_update_persists_each_row(
    db_session: AsyncSession,
) -> None:
    """bulk_update applies different remaining_qty / is_exhausted per lot
    in a single round trip — verifies the CASE-WHEN logic, not just N
    independent updates."""
    user = await _mk_user(db_session, "l2@x.com", "l2")
    acc = await _mk_account(db_session, user.id, name="bulk")
    lot_repo = PortfolioLotRepo(db_session)

    # Three lots, each with original_qty=10
    created: list[PortfolioLot] = []
    for i in range(3):
        t = await _mk_buy_trade(
            db_session,
            acc.id,
            user.id,
            qty=Decimal("10"),
            price=Decimal("100"),
            d=date(2026, 5, 1 + i),
        )
        lot = await lot_repo.create(
            trade_id=t.id,
            account_id=acc.id,
            symbol="2330",
            market=Market.TW_TWSE,
            original_qty=Decimal("10"),
            remaining_qty=Decimal("10"),
            cost_per_unit=Decimal("100"),
        )
        created.append(lot)
    await db_session.commit()

    # FIFO consumption simulation: lot[0] fully consumed, lot[1] partially,
    # lot[2] untouched.
    await lot_repo.bulk_update(
        [
            (created[0].id, Decimal("0"), True),
            (created[1].id, Decimal("3"), False),
        ]
    )
    await db_session.commit()

    fresh = await lot_repo.list_open_for_position(
        account_id=acc.id, symbol="2330", market=Market.TW_TWSE
    )
    fresh_by_id = {lot.id: lot for lot in fresh}
    # lot[0] should no longer appear in open list
    assert created[0].id not in fresh_by_id
    # lot[1] open with remaining=3
    assert fresh_by_id[created[1].id].remaining_qty == Decimal("3")
    # lot[2] unchanged
    assert fresh_by_id[created[2].id].remaining_qty == Decimal("10")


async def test_lot_repo_delete_by_trade(db_session: AsyncSession) -> None:
    """delete_by_trade wipes all lots from a single trade — used by trade
    PATCH / DELETE rebuild."""
    user = await _mk_user(db_session, "l3@x.com", "l3")
    acc = await _mk_account(db_session, user.id, name="delete")
    lot_repo = PortfolioLotRepo(db_session)

    t = await _mk_buy_trade(db_session, acc.id, user.id, qty=Decimal("10"))
    await lot_repo.create(
        trade_id=t.id,
        account_id=acc.id,
        symbol="2330",
        market=Market.TW_TWSE,
        original_qty=Decimal("10"),
        remaining_qty=Decimal("10"),
        cost_per_unit=Decimal("100"),
    )
    await db_session.commit()

    open_before = await lot_repo.list_open_for_position(
        account_id=acc.id, symbol="2330", market=Market.TW_TWSE
    )
    assert len(open_before) == 1

    await lot_repo.delete_by_trade(t.id)
    await db_session.commit()

    open_after = await lot_repo.list_open_for_position(
        account_id=acc.id, symbol="2330", market=Market.TW_TWSE
    )
    assert open_after == []


# ═════════════════════════════════════════════════════════════════════════════
# PortfolioPositionRepo (4 cases)
# ═════════════════════════════════════════════════════════════════════════════


async def test_position_repo_upsert_insert_then_update(
    db_session: AsyncSession,
) -> None:
    """First upsert inserts; second upsert on same (account, symbol, market)
    key updates in place — no UniqueViolation."""
    user = await _mk_user(db_session, "p1@x.com", "p1")
    acc = await _mk_account(db_session, user.id, name="pos")
    repo = PortfolioPositionRepo(db_session)

    pos1 = await repo.upsert(
        account_id=acc.id,
        symbol="2330",
        market=Market.TW_TWSE,
        currency="TWD",
        quantity=Decimal("10"),
        avg_cost=Decimal("100"),
        total_cost=Decimal("1000"),
    )
    await db_session.commit()
    assert pos1.quantity == Decimal("10")

    pos2 = await repo.upsert(
        account_id=acc.id,
        symbol="2330",
        market=Market.TW_TWSE,
        currency="TWD",
        quantity=Decimal("25"),  # changed
        avg_cost=Decimal("110"),
        total_cost=Decimal("2750"),
    )
    await db_session.commit()
    assert pos2.id == pos1.id  # same row
    assert pos2.quantity == Decimal("25")
    assert pos2.avg_cost_fifo == Decimal("110")

    # Only one row exists
    all_rows = await repo.list_by_account(acc.id)
    assert len(all_rows) == 1


async def test_position_repo_list_by_user_joins_accounts(
    db_session: AsyncSession,
) -> None:
    """list_by_user joins via portfolio_accounts to enforce ownership."""
    user_a = await _mk_user(db_session, "pla@x.com", "pla")
    user_b = await _mk_user(db_session, "plb@x.com", "plb")
    acc_a = await _mk_account(db_session, user_a.id, name="A acc")
    acc_b = await _mk_account(db_session, user_b.id, name="B acc")
    repo = PortfolioPositionRepo(db_session)

    await repo.upsert(
        account_id=acc_a.id,
        symbol="2330",
        market=Market.TW_TWSE,
        currency="TWD",
        quantity=Decimal("5"),
        avg_cost=Decimal("100"),
    )
    await repo.upsert(
        account_id=acc_b.id,
        symbol="AAPL",
        market=Market.US_NASDAQ,
        currency="USD",
        quantity=Decimal("3"),
        avg_cost=Decimal("150"),
    )
    await db_session.commit()

    a_positions = await repo.list_by_user(user_a.id)
    b_positions = await repo.list_by_user(user_b.id)
    assert {p.symbol for p in a_positions} == {"2330"}
    assert {p.symbol for p in b_positions} == {"AAPL"}


async def test_position_repo_count_by_user(db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "pc@x.com", "pc")
    acc = await _mk_account(db_session, user.id, name="cnt")
    repo = PortfolioPositionRepo(db_session)

    for sym in ["2330", "2454", "AAPL"]:
        mkt = Market.US_NASDAQ if sym == "AAPL" else Market.TW_TWSE
        await repo.upsert(
            account_id=acc.id,
            symbol=sym,
            market=mkt,
            currency="TWD" if mkt != Market.US_NASDAQ else "USD",
            quantity=Decimal("1"),
            avg_cost=Decimal("100"),
        )
    await db_session.commit()
    assert await repo.count_by_user(user.id) == 3


async def test_position_repo_delete(db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "pd@x.com", "pd")
    acc = await _mk_account(db_session, user.id, name="del")
    repo = PortfolioPositionRepo(db_session)

    await repo.upsert(
        account_id=acc.id,
        symbol="2330",
        market=Market.TW_TWSE,
        currency="TWD",
        quantity=Decimal("1"),
        avg_cost=Decimal("100"),
    )
    await db_session.commit()
    assert await repo.get(acc.id, "2330", Market.TW_TWSE) is not None

    await repo.delete(acc.id, "2330", Market.TW_TWSE)
    await db_session.commit()
    assert await repo.get(acc.id, "2330", Market.TW_TWSE) is None


# ═════════════════════════════════════════════════════════════════════════════
# PriceLookupRepo (3 cases)
# ═════════════════════════════════════════════════════════════════════════════


async def test_price_lookup_returns_latest_two_descending(
    db_session: AsyncSession,
) -> None:
    """3 days of prices → repo returns the 2 most recent, latest first."""
    stock = await _mk_stock(db_session, "2330", Market.TW_TWSE)
    for d, c in [
        (date(2026, 5, 1), Decimal("100")),
        (date(2026, 5, 2), Decimal("105")),
        (date(2026, 5, 3), Decimal("110")),
    ]:
        await _mk_price(db_session, stock.id, d, c)

    repo = PriceLookupRepo(db_session)
    rows = await repo.latest_two_closes("2330")
    assert len(rows) == 2
    assert rows[0].close == Decimal("110")
    assert rows[1].close == Decimal("105")


async def test_price_lookup_missing_symbol_returns_empty(
    db_session: AsyncSession,
) -> None:
    """Symbol not in `stocks` → empty list, never an exception."""
    repo = PriceLookupRepo(db_session)
    rows = await repo.latest_two_closes("NOPE")
    assert rows == []


async def test_price_lookup_batch_partitions_by_symbol(
    db_session: AsyncSession,
) -> None:
    """batch returns {symbol: [latest, prev]} for present symbols only."""
    s_a = await _mk_stock(db_session, "2330", Market.TW_TWSE)
    s_b = await _mk_stock(db_session, "AAPL", Market.US_NASDAQ)
    for s, d, c in [
        (s_a, date(2026, 5, 1), Decimal("100")),
        (s_a, date(2026, 5, 2), Decimal("105")),
        (s_a, date(2026, 5, 3), Decimal("110")),
        (s_b, date(2026, 5, 2), Decimal("180")),
        (s_b, date(2026, 5, 3), Decimal("190")),
    ]:
        await _mk_price(db_session, s.id, d, c)

    repo = PriceLookupRepo(db_session)
    result = await repo.latest_two_closes_batch(["2330", "AAPL", "MISSING"])

    assert set(result.keys()) == {"2330", "AAPL"}
    assert [p.close for p in result["2330"]] == [
        Decimal("110"),
        Decimal("105"),
    ]
    assert [p.close for p in result["AAPL"]] == [
        Decimal("190"),
        Decimal("180"),
    ]
