"""Integration tests for `PortfolioDividendRepo.get_monthly_dividend_summary`
— K4 婆媽 "本月股息收入" widget aggregation.

Verifies the repo's single grouped query (against the shared in-memory
SQLite `db_session` fixture) honours every business rule the widget
depends on:

- "本月" basis = ``COALESCE(pay_date, ex_dividend_date)`` (cash-received
  date; falls back to ex-date when pay_date is NULL).
- Money figures (`gross_amount` / `net_amount`) count CASH dividends
  ONLY — STOCK 配股 `amount_per_share` is a ratio, not cash, and must be
  excluded from the income total.
- `net_amount` = gross − withholding_tax.
- STOCK rows are counted separately into `stock_count` (optional badge).
- Window is half-open ``[month_start, next_month_start)``; rows on either
  edge of the boundary are included / excluded correctly.
- User isolation: another user's dividends never leak into the total.
- Empty case returns zeros, not NULLs.

`today` is injected so the window is deterministic regardless of when CI
runs (no flakiness at month boundaries).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from app.models.enums import Market, UserTier
from app.models.user import User
from app.repositories.portfolio import PortfolioAccountRepo, PortfolioDividendRepo

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _mk_user(db: AsyncSession, email: str) -> User:
    u = User(email=email, hashed_password="x" * 60, username=email.split("@")[0])
    u.tier = UserTier.PRO
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _mk_account(db: AsyncSession, user_id: int, name: str = "acc") -> int:
    acc = await PortfolioAccountRepo(db).create(user_id=user_id, name=name, market=Market.TW_TWSE)
    await db.commit()
    assert acc is not None
    return acc.id


async def _add_cash(
    db: AsyncSession,
    repo: PortfolioDividendRepo,
    *,
    account_id: int,
    user_id: int,
    amount_per_share: str,
    quantity: str,
    withholding_tax: str = "0",
    ex_date: date,
    pay_date: date | None = None,
    symbol: str = "2330",
) -> None:
    await repo.create(
        account_id=account_id,
        user_id=user_id,
        symbol=symbol,
        market=Market.TW_TWSE,
        dividend_type="CASH",
        ex_dividend_date=ex_date,
        pay_date=pay_date,
        amount_per_share=Decimal(amount_per_share),
        quantity_at_record=Decimal(quantity),
        withholding_tax=Decimal(withholding_tax),
        currency="TWD",
    )
    await db.commit()


async def _add_stock(
    db: AsyncSession,
    repo: PortfolioDividendRepo,
    *,
    account_id: int,
    user_id: int,
    ratio: str,
    quantity: str,
    ex_date: date,
    pay_date: date | None = None,
    symbol: str = "2330",
) -> None:
    await repo.create(
        account_id=account_id,
        user_id=user_id,
        symbol=symbol,
        market=Market.TW_TWSE,
        dividend_type="STOCK",
        ex_dividend_date=ex_date,
        pay_date=pay_date,
        amount_per_share=Decimal(ratio),  # service stores ratio here
        quantity_at_record=Decimal(quantity),
        withholding_tax=Decimal("0"),
        currency="TWD",
    )
    await db.commit()


_JUN = date(2026, 6, 6)  # "today" used to anchor the June 2026 window


async def test_monthly_summary_empty_returns_zeros(db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "mds_empty@x.tw")
    repo = PortfolioDividendRepo(db_session)
    summary = await repo.get_monthly_dividend_summary(user.id, today=_JUN)
    assert summary.month == "2026-06"
    assert summary.gross_amount == Decimal("0")
    assert summary.net_amount == Decimal("0")
    assert summary.cash_count == 0
    assert summary.stock_count == 0


async def test_monthly_summary_cash_only_sums_gross_and_net(
    db_session: AsyncSession,
) -> None:
    """CASH gross = Σ aps×qty; net = gross − withholding."""
    user = await _mk_user(db_session, "mds_cash@x.tw")
    aid = await _mk_account(db_session, user.id)
    repo = PortfolioDividendRepo(db_session)
    # 5 × 100 = 500 gross, 50 tax → 450 net
    await _add_cash(
        db_session,
        repo,
        account_id=aid,
        user_id=user.id,
        amount_per_share="5",
        quantity="100",
        withholding_tax="50",
        ex_date=date(2026, 6, 1),
        pay_date=date(2026, 6, 10),
    )
    # 2 × 200 = 400 gross, 0 tax → 400 net
    await _add_cash(
        db_session,
        repo,
        account_id=aid,
        user_id=user.id,
        amount_per_share="2",
        quantity="200",
        ex_date=date(2026, 6, 2),
        pay_date=date(2026, 6, 15),
        symbol="2317",
    )
    summary = await repo.get_monthly_dividend_summary(user.id, today=_JUN)
    assert summary.gross_amount == Decimal("900")
    assert summary.net_amount == Decimal("850")
    assert summary.cash_count == 2
    assert summary.stock_count == 0


async def test_monthly_summary_excludes_stock_from_money(
    db_session: AsyncSession,
) -> None:
    """STOCK 配股 ratio must NOT contribute to gross/net; it only bumps
    stock_count."""
    user = await _mk_user(db_session, "mds_stock@x.tw")
    aid = await _mk_account(db_session, user.id)
    repo = PortfolioDividendRepo(db_session)
    await _add_cash(
        db_session,
        repo,
        account_id=aid,
        user_id=user.id,
        amount_per_share="3",
        quantity="100",
        ex_date=date(2026, 6, 1),
        pay_date=date(2026, 6, 5),
    )
    await _add_stock(
        db_session,
        repo,
        account_id=aid,
        user_id=user.id,
        ratio="0.2",
        quantity="100",
        ex_date=date(2026, 6, 3),
        pay_date=date(2026, 6, 8),
    )
    summary = await repo.get_monthly_dividend_summary(user.id, today=_JUN)
    # Only the CASH row's 3×100 = 300 counts.
    assert summary.gross_amount == Decimal("300")
    assert summary.net_amount == Decimal("300")
    assert summary.cash_count == 1
    assert summary.stock_count == 1


async def test_monthly_summary_uses_pay_date_basis(db_session: AsyncSession) -> None:
    """A dividend whose ex-date is in May but pay_date is in June counts
    in June (cash actually received in June)."""
    user = await _mk_user(db_session, "mds_paydate@x.tw")
    aid = await _mk_account(db_session, user.id)
    repo = PortfolioDividendRepo(db_session)
    await _add_cash(
        db_session,
        repo,
        account_id=aid,
        user_id=user.id,
        amount_per_share="4",
        quantity="100",
        ex_date=date(2026, 5, 28),
        pay_date=date(2026, 6, 2),
    )
    summary = await repo.get_monthly_dividend_summary(user.id, today=_JUN)
    assert summary.gross_amount == Decimal("400")
    assert summary.cash_count == 1


async def test_monthly_summary_pay_date_in_may_excluded(
    db_session: AsyncSession,
) -> None:
    """ex-date in June but pay_date in May → cash received in May → NOT in
    June total (pay_date wins over ex-date)."""
    user = await _mk_user(db_session, "mds_paymay@x.tw")
    aid = await _mk_account(db_session, user.id)
    repo = PortfolioDividendRepo(db_session)
    await _add_cash(
        db_session,
        repo,
        account_id=aid,
        user_id=user.id,
        amount_per_share="9",
        quantity="100",
        ex_date=date(2026, 6, 1),
        pay_date=date(2026, 5, 30),
    )
    summary = await repo.get_monthly_dividend_summary(user.id, today=_JUN)
    assert summary.gross_amount == Decimal("0")
    assert summary.cash_count == 0


async def test_monthly_summary_null_pay_date_falls_back_to_ex_date(
    db_session: AsyncSession,
) -> None:
    """pay_date NULL → COALESCE uses ex_dividend_date for the window."""
    user = await _mk_user(db_session, "mds_nullpay@x.tw")
    aid = await _mk_account(db_session, user.id)
    repo = PortfolioDividendRepo(db_session)
    await _add_cash(
        db_session,
        repo,
        account_id=aid,
        user_id=user.id,
        amount_per_share="6",
        quantity="100",
        ex_date=date(2026, 6, 4),
        pay_date=None,
    )
    summary = await repo.get_monthly_dividend_summary(user.id, today=_JUN)
    assert summary.gross_amount == Decimal("600")
    assert summary.cash_count == 1


async def test_monthly_summary_window_boundaries(db_session: AsyncSession) -> None:
    """month_start inclusive, next_month_start exclusive."""
    user = await _mk_user(db_session, "mds_bound@x.tw")
    aid = await _mk_account(db_session, user.id)
    repo = PortfolioDividendRepo(db_session)
    # Jun 1 → included
    await _add_cash(
        db_session,
        repo,
        account_id=aid,
        user_id=user.id,
        amount_per_share="1",
        quantity="100",
        ex_date=date(2026, 6, 1),
        pay_date=date(2026, 6, 1),
    )
    # Jul 1 → excluded
    await _add_cash(
        db_session,
        repo,
        account_id=aid,
        user_id=user.id,
        amount_per_share="7",
        quantity="100",
        ex_date=date(2026, 7, 1),
        pay_date=date(2026, 7, 1),
        symbol="2317",
    )
    # May 31 → excluded
    await _add_cash(
        db_session,
        repo,
        account_id=aid,
        user_id=user.id,
        amount_per_share="5",
        quantity="100",
        ex_date=date(2026, 5, 31),
        pay_date=date(2026, 5, 31),
        symbol="2454",
    )
    summary = await repo.get_monthly_dividend_summary(user.id, today=_JUN)
    assert summary.gross_amount == Decimal("100")  # only the Jun-1 row
    assert summary.cash_count == 1


async def test_monthly_summary_user_isolation(db_session: AsyncSession) -> None:
    """User B's dividends never bleed into User A's total."""
    a = await _mk_user(db_session, "mds_a@x.tw")
    b = await _mk_user(db_session, "mds_b@x.tw")
    aid_a = await _mk_account(db_session, a.id, name="a")
    aid_b = await _mk_account(db_session, b.id, name="b")
    repo = PortfolioDividendRepo(db_session)
    await _add_cash(
        db_session,
        repo,
        account_id=aid_a,
        user_id=a.id,
        amount_per_share="10",
        quantity="100",
        ex_date=date(2026, 6, 5),
        pay_date=date(2026, 6, 5),
    )
    await _add_cash(
        db_session,
        repo,
        account_id=aid_b,
        user_id=b.id,
        amount_per_share="99",
        quantity="100",
        ex_date=date(2026, 6, 5),
        pay_date=date(2026, 6, 5),
    )
    summary_a = await repo.get_monthly_dividend_summary(a.id, today=_JUN)
    assert summary_a.gross_amount == Decimal("1000")
    assert summary_a.cash_count == 1


async def test_monthly_summary_december_rolls_to_january(
    db_session: AsyncSession,
) -> None:
    """The Dec→Jan year roll must not throw and must exclude Jan rows."""
    user = await _mk_user(db_session, "mds_dec@x.tw")
    aid = await _mk_account(db_session, user.id)
    repo = PortfolioDividendRepo(db_session)
    await _add_cash(
        db_session,
        repo,
        account_id=aid,
        user_id=user.id,
        amount_per_share="8",
        quantity="100",
        ex_date=date(2026, 12, 15),
        pay_date=date(2026, 12, 15),
    )
    # Jan 2027 → excluded by next_month_start.
    await _add_cash(
        db_session,
        repo,
        account_id=aid,
        user_id=user.id,
        amount_per_share="3",
        quantity="100",
        ex_date=date(2027, 1, 2),
        pay_date=date(2027, 1, 2),
        symbol="2317",
    )
    summary = await repo.get_monthly_dividend_summary(user.id, today=date(2026, 12, 20))
    assert summary.month == "2026-12"
    assert summary.gross_amount == Decimal("800")
    assert summary.cash_count == 1
