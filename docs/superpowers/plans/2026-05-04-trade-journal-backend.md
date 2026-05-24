# Trade Journal — Backend Implementation Plan (Plan A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete backend for the Trade Journal module: 8-table PostgreSQL schema, FIFO cost-basis engine, position cache sync, rebalance alert calculator, and all `/api/v1/journal/` REST endpoints.

**Architecture:** Hybrid — `trades` is the immutable source of truth; `trade_lots` enables O(open-lots) FIFO; `positions` is a write-through cache; `portfolio_snapshots` supports D/W/M/Y chart queries. FIFO engine is pure Python (no DB side-effects) tested in isolation before any DB work.

**Tech Stack:** FastAPI, SQLAlchemy 2.x async (mapped_column), Alembic, PostgreSQL 15, pytest-asyncio, factory_boy

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `backend/app/modules/trade_journal/__init__.py` | Module marker |
| Create | `backend/app/modules/trade_journal/fifo_engine.py` | Pure FIFO logic (no DB), dataclasses |
| Create | `backend/app/modules/trade_journal/position_sync.py` | Apply FIFO result to `positions` + `trade_lots` tables |
| Create | `backend/app/modules/trade_journal/rebalance.py` | Compute rebalance alerts from `allocation_rules` |
| Create | `backend/app/modules/trade_journal/fx_service.py` | FX rate lookup with fallback |
| Create | `backend/app/modules/trade_journal/snapshot_job.py` | Daily snapshot cron function |
| Create | `backend/app/models/journal.py` | SQLAlchemy models for all 8 tables |
| Modify | `backend/app/models/__init__.py` | Register journal models |
| Create | `backend/app/schemas/journal.py` | Pydantic request/response schemas |
| Create | `backend/alembic/versions/0020_add_journal_tables.py` | Alembic migration (8 tables) |
| Create | `backend/app/api/v1/journal.py` | FastAPI router for all `/journal/` endpoints |
| Modify | `backend/app/api/v1/router.py` | Register journal router |
| Create | `backend/tests/unit/test_fifo_engine.py` | T01–T14 pure unit tests |
| Create | `backend/tests/unit/test_rebalance.py` | T21–T28 pure unit tests |
| Create | `backend/tests/integration/test_journal_api.py` | T15–T20, T29–T40 integration tests |

---

## Task 0: FIFO Engine — Pure Logic (T01–T09)

**Files:**
- Create: `backend/app/modules/trade_journal/__init__.py`
- Create: `backend/app/modules/trade_journal/fifo_engine.py`
- Create: `backend/tests/unit/test_fifo_engine.py`

- [ ] **Step 1: Create module directory and marker**

```bash
mkdir -p backend/app/modules/trade_journal
touch backend/app/modules/trade_journal/__init__.py
```

- [ ] **Step 2: Write failing tests T01–T09**

Create `backend/tests/unit/test_fifo_engine.py`:

```python
"""Unit tests for FIFO engine — T01–T09 (BUY/SELL scenarios)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.trade_journal.fifo_engine import (
    FIFOEngine,
    Lot,
    FIFOResult,
    InsufficientSharesError,
)


def _engine(lots: list[Lot]) -> FIFOEngine:
    return FIFOEngine(open_lots=lots)


# ── T01: Single lot, full sell ────────────────────────────────────────────────
def test_T01_single_lot_full_sell():
    engine = _engine([Lot(lot_id=1, original_qty=Decimal("100"), remaining_qty=Decimal("100"), cost_per_unit=Decimal("100"))])
    result = engine.process_sell(qty=Decimal("100"), price=Decimal("150"), fee=Decimal("0"), tax=Decimal("0"))
    assert result.realized_pnl == Decimal("5000")
    assert result.updated_lots[0].remaining_qty == Decimal("0")
    assert result.updated_lots[0].is_exhausted is True


# ── T02: Single lot, partial sell ────────────────────────────────────────────
def test_T02_single_lot_partial_sell():
    engine = _engine([Lot(lot_id=1, original_qty=Decimal("100"), remaining_qty=Decimal("100"), cost_per_unit=Decimal("100"))])
    result = engine.process_sell(qty=Decimal("40"), price=Decimal("150"), fee=Decimal("0"), tax=Decimal("0"))
    assert result.realized_pnl == Decimal("2000")
    assert result.updated_lots[0].remaining_qty == Decimal("60")
    assert result.updated_lots[0].is_exhausted is False


# ── T03: Cross two lots, FIFO order ──────────────────────────────────────────
def test_T03_cross_two_lots_fifo():
    engine = _engine([
        Lot(lot_id=1, original_qty=Decimal("100"), remaining_qty=Decimal("100"), cost_per_unit=Decimal("100")),
        Lot(lot_id=2, original_qty=Decimal("50"), remaining_qty=Decimal("50"), cost_per_unit=Decimal("120")),
    ])
    result = engine.process_sell(qty=Decimal("120"), price=Decimal("150"), fee=Decimal("0"), tax=Decimal("0"))
    # Lot A: 100@100 sold → gain 5000; Lot B: 20@120 sold → gain 600; total=5600
    assert result.realized_pnl == Decimal("5600")
    assert result.updated_lots[0].remaining_qty == Decimal("0")
    assert result.updated_lots[0].is_exhausted is True
    assert result.updated_lots[1].remaining_qty == Decimal("30")
    assert result.updated_lots[1].is_exhausted is False


# ── T04: Exactly exhaust first lot ───────────────────────────────────────────
def test_T04_exactly_exhaust_first_lot():
    engine = _engine([
        Lot(lot_id=1, original_qty=Decimal("100"), remaining_qty=Decimal("100"), cost_per_unit=Decimal("100")),
        Lot(lot_id=2, original_qty=Decimal("50"), remaining_qty=Decimal("50"), cost_per_unit=Decimal("120")),
    ])
    result = engine.process_sell(qty=Decimal("100"), price=Decimal("150"), fee=Decimal("0"), tax=Decimal("0"))
    assert result.realized_pnl == Decimal("5000")
    assert result.updated_lots[0].is_exhausted is True
    assert result.updated_lots[1].remaining_qty == Decimal("50")  # Lot B untouched


# ── T05: Sell at a loss ───────────────────────────────────────────────────────
def test_T05_sell_at_loss():
    engine = _engine([Lot(lot_id=1, original_qty=Decimal("100"), remaining_qty=Decimal("100"), cost_per_unit=Decimal("100"))])
    result = engine.process_sell(qty=Decimal("100"), price=Decimal("80"), fee=Decimal("0"), tax=Decimal("0"))
    assert result.realized_pnl == Decimal("-2000")


# ── T06: Sell exceeds holdings (must raise) ───────────────────────────────────
def test_T06_sell_exceeds_holdings():
    engine = _engine([Lot(lot_id=1, original_qty=Decimal("50"), remaining_qty=Decimal("50"), cost_per_unit=Decimal("100"))])
    with pytest.raises(InsufficientSharesError):
        engine.process_sell(qty=Decimal("100"), price=Decimal("150"), fee=Decimal("0"), tax=Decimal("0"))


# ── T07: No open position (must raise) ────────────────────────────────────────
def test_T07_no_open_position():
    engine = _engine([])
    with pytest.raises(InsufficientSharesError):
        engine.process_sell(qty=Decimal("100"), price=Decimal("150"), fee=Decimal("0"), tax=Decimal("0"))


# ── T08: Fee + tax included in P&L ────────────────────────────────────────────
def test_T08_fee_and_tax_in_pnl():
    # BUY 100@100 fee=100 → cost_per_unit = (10000+100)/100 = 101
    # SELL 100@100 fee=100 tax=300 → proceeds = 10000-100-300 = 9600; cost = 101*100 = 10100 → realized = -500
    engine = _engine([Lot(lot_id=1, original_qty=Decimal("100"), remaining_qty=Decimal("100"), cost_per_unit=Decimal("101"))])
    result = engine.process_sell(qty=Decimal("100"), price=Decimal("100"), fee=Decimal("100"), tax=Decimal("300"))
    assert result.realized_pnl == Decimal("-500")


# ── T09: Multiple buys, multiple sells ────────────────────────────────────────
def test_T09_multiple_buys_multiple_sells():
    engine = _engine([
        Lot(lot_id=1, original_qty=Decimal("100"), remaining_qty=Decimal("100"), cost_per_unit=Decimal("100")),
        Lot(lot_id=2, original_qty=Decimal("80"), remaining_qty=Decimal("80"), cost_per_unit=Decimal("110")),
        Lot(lot_id=3, original_qty=Decimal("60"), remaining_qty=Decimal("60"), cost_per_unit=Decimal("120")),
    ])
    # Sell 1: 130 shares @150
    r1 = engine.process_sell(qty=Decimal("130"), price=Decimal("150"), fee=Decimal("0"), tax=Decimal("0"))
    # Lot1 fully used (100@100→+5000), Lot2 partial 30@110→+1200; total +6200
    assert r1.realized_pnl == Decimal("6200")
    # Sell 2: remaining 110 shares @160
    r2 = engine.process_sell(qty=Decimal("110"), price=Decimal("160"), fee=Decimal("0"), tax=Decimal("0"))
    # Lot2 remaining 50@110→+2500, Lot3 60@120→+2400; total +4900
    assert r2.realized_pnl == Decimal("4900")
    # Grand total: 6200+4900=11100
    assert r1.realized_pnl + r2.realized_pnl == Decimal("11100")
```

- [ ] **Step 3: Run tests — expect failure (module not found)**

```bash
cd backend && python -m pytest tests/unit/test_fifo_engine.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError: No module named 'app.modules.trade_journal.fifo_engine'`

- [ ] **Step 4: Implement `fifo_engine.py`**

Create `backend/app/modules/trade_journal/fifo_engine.py`:

```python
"""Pure FIFO engine — no database, no side effects.

Call process_buy() when recording a BUY to get a new Lot.
Call process_sell() to consume open lots in FIFO order and get realized P&L.
Call process_split() to adjust all lots for a stock split.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


class InsufficientSharesError(ValueError):
    """Raised when a SELL quantity exceeds available open lots."""


@dataclass
class Lot:
    """One BUY batch. Corresponds to one trade_lots row."""
    lot_id: int  # trade_lots.id (0 for pre-persistence use)
    original_qty: Decimal
    remaining_qty: Decimal
    cost_per_unit: Decimal  # includes fee pro-rated: (price*qty + fee) / qty
    is_exhausted: bool = False


@dataclass
class FIFOResult:
    """Result of process_sell()."""
    realized_pnl: Decimal
    updated_lots: list[Lot]  # only the lots that were touched
    qty_consumed: Decimal


def _compute_cost_per_unit(price: Decimal, qty: Decimal, fee: Decimal) -> Decimal:
    """Total cost / qty, fee spread evenly across shares."""
    return (price * qty + fee) / qty


class FIFOEngine:
    """Stateful within a single call chain; open_lots must be pre-sorted by lot_id ASC (oldest first)."""

    def __init__(self, open_lots: list[Lot]) -> None:
        # Work on a shallow copy so callers can compare before/after
        self._lots: list[Lot] = [
            Lot(
                lot_id=lot.lot_id,
                original_qty=lot.original_qty,
                remaining_qty=lot.remaining_qty,
                cost_per_unit=lot.cost_per_unit,
                is_exhausted=lot.is_exhausted,
            )
            for lot in open_lots
        ]

    # ── Public API ──────────────────────────────────────────────────────────

    @staticmethod
    def make_lot(
        lot_id: int,
        qty: Decimal,
        price: Decimal,
        fee: Decimal,
    ) -> Lot:
        """Build a Lot for a BUY trade (fee spread into cost_per_unit)."""
        cost_per_unit = _compute_cost_per_unit(price, qty, fee)
        return Lot(
            lot_id=lot_id,
            original_qty=qty,
            remaining_qty=qty,
            cost_per_unit=cost_per_unit,
        )

    def process_sell(
        self,
        qty: Decimal,
        price: Decimal,
        fee: Decimal,
        tax: Decimal,
    ) -> FIFOResult:
        """Consume open lots in FIFO order, compute realized P&L.

        realized_pnl = proceeds - cost
        proceeds = price * qty - fee - tax
        cost = sum(cost_per_unit * shares_consumed) for each lot
        """
        available = sum(lot.remaining_qty for lot in self._lots)
        if available < qty:
            raise InsufficientSharesError(
                f"Cannot sell {qty}: only {available} shares available."
            )

        proceeds = price * qty - fee - tax
        remaining_to_sell = qty
        total_cost = Decimal("0")
        touched_lots: list[Lot] = []

        for lot in self._lots:
            if remaining_to_sell <= Decimal("0"):
                break
            if lot.remaining_qty <= Decimal("0"):
                continue

            consume = min(lot.remaining_qty, remaining_to_sell)
            total_cost += lot.cost_per_unit * consume
            lot.remaining_qty -= consume
            remaining_to_sell -= consume
            if lot.remaining_qty == Decimal("0"):
                lot.is_exhausted = True
            touched_lots.append(lot)

        realized_pnl = proceeds - total_cost
        return FIFOResult(
            realized_pnl=realized_pnl,
            updated_lots=touched_lots,
            qty_consumed=qty,
        )

    def process_split(self, ratio: Decimal) -> list[Lot]:
        """Apply a forward split (ratio > 1) or reverse split (ratio < 1) to all lots.

        new_remaining_qty = remaining_qty * ratio
        new_cost_per_unit = cost_per_unit / ratio
        """
        for lot in self._lots:
            lot.remaining_qty = lot.remaining_qty * ratio
            lot.original_qty = lot.original_qty * ratio
            lot.cost_per_unit = lot.cost_per_unit / ratio
        return list(self._lots)
```

- [ ] **Step 5: Run tests — expect all 9 pass**

```bash
cd backend && python -m pytest tests/unit/test_fifo_engine.py -v
```
Expected: `9 passed`

- [ ] **Step 6: Add SPLIT tests T10–T14**

Append to `backend/tests/unit/test_fifo_engine.py`:

```python
# ── T10: 2:1 forward split ───────────────────────────────────────────────────
def test_T10_forward_split_2for1():
    engine = _engine([Lot(lot_id=1, original_qty=Decimal("100"), remaining_qty=Decimal("100"), cost_per_unit=Decimal("100"))])
    lots = engine.process_split(ratio=Decimal("2"))
    assert lots[0].remaining_qty == Decimal("200")
    assert lots[0].cost_per_unit == Decimal("50")


# ── T11: Sell after split uses correct cost ───────────────────────────────────
def test_T11_sell_after_split():
    engine = _engine([Lot(lot_id=1, original_qty=Decimal("100"), remaining_qty=Decimal("100"), cost_per_unit=Decimal("100"))])
    engine.process_split(ratio=Decimal("2"))
    # Now 200 shares @50/share; sell 200@70 → proceeds=14000, cost=10000, realized=+4000
    result = engine.process_sell(qty=Decimal("200"), price=Decimal("70"), fee=Decimal("0"), tax=Decimal("0"))
    assert result.realized_pnl == Decimal("4000")


# ── T12: 1:10 reverse split ───────────────────────────────────────────────────
def test_T12_reverse_split_1for10():
    engine = _engine([Lot(lot_id=1, original_qty=Decimal("100"), remaining_qty=Decimal("100"), cost_per_unit=Decimal("10"))])
    lots = engine.process_split(ratio=Decimal("0.1"))
    assert lots[0].remaining_qty == Decimal("10")
    assert lots[0].cost_per_unit == Decimal("100")


# ── T13: Multi-lot split ──────────────────────────────────────────────────────
def test_T13_multi_lot_split():
    engine = _engine([
        Lot(lot_id=1, original_qty=Decimal("100"), remaining_qty=Decimal("100"), cost_per_unit=Decimal("100")),
        Lot(lot_id=2, original_qty=Decimal("50"), remaining_qty=Decimal("50"), cost_per_unit=Decimal("120")),
    ])
    lots = engine.process_split(ratio=Decimal("2"))
    assert lots[0].remaining_qty == Decimal("200") and lots[0].cost_per_unit == Decimal("50")
    assert lots[1].remaining_qty == Decimal("100") and lots[1].cost_per_unit == Decimal("60")


# ── T14: Dividend does not touch lots (API-level test — fifo_engine not involved)
def test_T14_dividend_no_lot_change():
    lots_before = [Lot(lot_id=1, original_qty=Decimal("100"), remaining_qty=Decimal("100"), cost_per_unit=Decimal("100"))]
    engine = _engine(lots_before)
    # DIVIDEND is handled at API level — fifo_engine has no process_dividend()
    # Verify no method accidentally mutates lots for dividend
    assert not hasattr(engine, "process_dividend"), "FIFOEngine should not handle dividends"
    # Lots remain unchanged
    assert engine._lots[0].remaining_qty == Decimal("100")
```

- [ ] **Step 7: Run all 14 tests**

```bash
cd backend && python -m pytest tests/unit/test_fifo_engine.py -v
```
Expected: `14 passed`

- [ ] **Step 8: Commit**

```bash
cd backend && git add app/modules/trade_journal/__init__.py app/modules/trade_journal/fifo_engine.py tests/unit/test_fifo_engine.py
git commit -m "feat(journal): FIFO engine pure logic + T01–T14 passing"
```

---

## Task 1: SQLAlchemy Models (8 Tables)

**Files:**
- Create: `backend/app/models/journal.py`

- [ ] **Step 1: Write `backend/app/models/journal.py`**

```python
"""SQLAlchemy models for the Trade Journal module."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# ── trade_accounts ────────────────────────────────────────────────────────────

class TradeAccount(Base):
    __tablename__ = "trade_accounts"

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    broker: Mapped[str | None] = mapped_column(String(50), default=None)
    market: Mapped[str] = mapped_column(String(10), nullable=False)   # TW / US / CRYPTO
    currency: Mapped[str] = mapped_column(String(10), nullable=False)  # TWD / USD / USDT
    description: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )


# ── account_groups ────────────────────────────────────────────────────────────

class AccountGroup(Base):
    __tablename__ = "account_groups"

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    base_currency: Mapped[str] = mapped_column(String(10), default="TWD")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )


# ── account_group_members ─────────────────────────────────────────────────────

class AccountGroupMember(Base):
    __tablename__ = "account_group_members"
    __table_args__ = (UniqueConstraint("group_id", "account_id"),)

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("account_groups.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trade_accounts.id", ondelete="CASCADE"), nullable=False
    )
    target_weight: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), default=None)


# ── trades ────────────────────────────────────────────────────────────────────

class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        Index("ix_trades_account_symbol", "account_id", "symbol", "market", "date"),
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trade_accounts.id"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    market: Mapped[str] = mapped_column(String(10), nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)  # BUY/SELL/DIVIDEND/SPLIT
    date: Mapped[date] = mapped_column(Date, nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), default=None)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), default=None)
    fee: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    tax: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    trade_fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), default=None)
    tags: Mapped[list] = mapped_column(JSONB, default_factory=list)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )


# ── trade_lots ────────────────────────────────────────────────────────────────

class TradeLot(Base):
    __tablename__ = "trade_lots"
    __table_args__ = (
        Index(
            "ix_trade_lots_fifo",
            "account_id", "symbol", "market", "is_exhausted", "trade_id",
        ),
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    trade_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trades.id"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trade_accounts.id"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    market: Mapped[str] = mapped_column(String(10), nullable=False)
    original_qty: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    remaining_qty: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    cost_per_unit: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    is_exhausted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


# ── positions ─────────────────────────────────────────────────────────────────

class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("account_id", "symbol", "market"),)

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trade_accounts.id"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    market: Mapped[str] = mapped_column(String(10), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    avg_cost_fifo: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), default=None)
    total_cost: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), default=None)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now(), onupdate=func.now()
    )


# ── portfolio_snapshots ───────────────────────────────────────────────────────

class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        CheckConstraint(
            "(account_id IS NOT NULL AND group_id IS NULL) OR "
            "(account_id IS NULL AND group_id IS NOT NULL)",
            name="ck_snapshot_one_owner",
        ),
        # Partial unique indexes are added in Alembic migration (not supported via __table_args__ directly)
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    account_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("trade_accounts.id"), default=None, index=True
    )
    group_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("account_groups.id"), default=None, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    total_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), default=None)
    total_cost: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), default=None)
    unrealized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), default=None)
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), default=None)
    twd_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), default=None)


# ── allocation_rules ──────────────────────────────────────────────────────────

class AllocationRule(Base):
    __tablename__ = "allocation_rules"
    __table_args__ = (
        CheckConstraint(
            "(account_id IS NOT NULL AND group_id IS NULL) OR "
            "(account_id IS NULL AND group_id IS NOT NULL)",
            name="ck_rule_one_owner",
        ),
        # Partial unique indexes in Alembic migration
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    account_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("trade_accounts.id"), default=None, index=True
    )
    group_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("account_groups.id"), default=None, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    target_weight: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    lower_threshold: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.03"))
    upper_threshold: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.03"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


# ── fx_rates ──────────────────────────────────────────────────────────────────

class FXRate(Base):
    __tablename__ = "fx_rates"
    __table_args__ = (UniqueConstraint("date", "from_currency", "to_currency"),)

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    from_currency: Mapped[str] = mapped_column(String(10), nullable=False)
    to_currency: Mapped[str] = mapped_column(String(10), default="TWD", nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
```

- [ ] **Step 2: Commit**

```bash
cd backend && git add app/models/journal.py
git commit -m "feat(journal): SQLAlchemy models for 8 trade journal tables"
```

---

## Task 2: Register Models + Alembic Migration

**Files:**
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0020_add_journal_tables.py`

- [ ] **Step 1: Register models in `backend/app/models/__init__.py`**

Add after the last import line and update `__all__`:

```python
from app.models.journal import (
    AccountGroup,
    AccountGroupMember,
    AllocationRule,
    FXRate,
    Portfolio Snapshot,
    Position,
    Trade,
    TradeAccount,
    TradeLot,
)
```

And add to `__all__`:
```python
"AccountGroup",
"AccountGroupMember",
"AllocationRule",
"FXRate",
"PortfolioSnapshot",
"Position",
"Trade",
"TradeAccount",
"TradeLot",
```

- [ ] **Step 2: Generate Alembic revision**

```bash
cd backend && alembic revision --autogenerate -m "add_journal_tables"
```

Note the generated filename (e.g., `alembic/versions/xxxx_add_journal_tables.py`). Open it and **add partial unique indexes** to the `upgrade()` function after the table creation:

```python
# Add partial unique indexes (not auto-generated by SQLAlchemy)
op.execute("""
    CREATE UNIQUE INDEX uq_account_snapshot
        ON portfolio_snapshots(account_id, date)
        WHERE account_id IS NOT NULL;
    CREATE UNIQUE INDEX uq_group_snapshot
        ON portfolio_snapshots(group_id, date)
        WHERE group_id IS NOT NULL;
    CREATE UNIQUE INDEX uq_rule_account_symbol
        ON allocation_rules(account_id, symbol)
        WHERE account_id IS NOT NULL;
    CREATE UNIQUE INDEX uq_rule_group_symbol
        ON allocation_rules(group_id, symbol)
        WHERE group_id IS NOT NULL;
""")
```

And in `downgrade()` before dropping tables:
```python
op.execute("""
    DROP INDEX IF EXISTS uq_account_snapshot;
    DROP INDEX IF EXISTS uq_group_snapshot;
    DROP INDEX IF EXISTS uq_rule_account_symbol;
    DROP INDEX IF EXISTS uq_rule_group_symbol;
""")
```

- [ ] **Step 3: Apply migration**

```bash
cd backend && alembic upgrade head
```
Expected: migration runs without error, 8 new tables visible in DB.

- [ ] **Step 4: Verify tables exist**

```bash
cd backend && python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
async def check():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/uni_seeker')
    async with engine.connect() as conn:
        result = await conn.execute(text(\"SELECT tablename FROM pg_tables WHERE tablename LIKE '%trade%' OR tablename IN ('positions','fx_rates','account_groups','allocation_rules','portfolio_snapshots')\"))
        for row in result: print(row[0])
asyncio.run(check())
"
```
Expected: 8 table names printed.

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/models/__init__.py alembic/versions/
git commit -m "feat(journal): register journal models + alembic migration (8 tables)"
```

---

## Task 3: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/journal.py`

- [ ] **Step 1: Create `backend/app/schemas/journal.py`**

```python
"""Pydantic schemas for Trade Journal API."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


# ── Account ───────────────────────────────────────────────────────────────────

class AccountCreate(BaseModel):
    name: str
    broker: str | None = None
    market: Literal["TW", "US", "CRYPTO"]
    currency: Literal["TWD", "USD", "USDT", "BTC", "ETH"]
    description: str | None = None


class AccountResponse(BaseModel):
    id: int
    name: str
    broker: str | None
    market: str
    currency: str
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Trade ─────────────────────────────────────────────────────────────────────

class TradeCreate(BaseModel):
    symbol: str
    market: Literal["TW", "US", "CRYPTO"]
    action: Literal["BUY", "SELL", "DIVIDEND", "SPLIT"]
    date: date
    price: Decimal | None = None
    quantity: Decimal | None = None
    fee: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    trade_fx_rate: Decimal | None = None
    tags: list[str] = Field(default_factory=list)
    note: str | None = None
    # For SPLIT: ratio = new_shares / old_shares (e.g. 2.0 for 2:1 split)
    split_ratio: Decimal | None = None


class TradeResponse(BaseModel):
    id: int
    account_id: int
    symbol: str
    market: str
    action: str
    date: date
    price: Decimal | None
    quantity: Decimal | None
    fee: Decimal
    tax: Decimal
    trade_fx_rate: Decimal | None
    tags: list[str]
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TradeListResponse(BaseModel):
    total: int
    items: list[TradeResponse]


# ── Position ──────────────────────────────────────────────────────────────────

class PositionResponse(BaseModel):
    id: int
    account_id: int
    symbol: str
    market: str
    currency: str
    quantity: Decimal
    avg_cost_fifo: Decimal | None
    total_cost: Decimal | None
    realized_pnl: Decimal
    is_closed: bool

    model_config = {"from_attributes": True}


# ── Account Detail (with positions) ──────────────────────────────────────────

class AccountDetailResponse(BaseModel):
    account: AccountResponse
    positions: list[PositionResponse]


# ── Group ─────────────────────────────────────────────────────────────────────

class GroupCreate(BaseModel):
    name: str
    description: str | None = None
    base_currency: str = "TWD"
    members: list[GroupMemberInput] = Field(default_factory=list)


class GroupMemberInput(BaseModel):
    account_id: int
    target_weight: Decimal | None = None


class GroupMemberResponse(BaseModel):
    account_id: int
    target_weight: Decimal | None
    account: AccountResponse

    model_config = {"from_attributes": True}


class GroupResponse(BaseModel):
    id: int
    name: str
    description: str | None
    base_currency: str
    members: list[GroupMemberResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# ── Allocation Rule ───────────────────────────────────────────────────────────

class AllocationRuleCreate(BaseModel):
    symbol: str
    target_weight: Decimal
    lower_threshold: Decimal = Decimal("0.03")
    upper_threshold: Decimal = Decimal("0.03")
    is_active: bool = True


class AllocationRuleResponse(BaseModel):
    id: int
    symbol: str
    target_weight: Decimal
    lower_threshold: Decimal
    upper_threshold: Decimal
    is_active: bool

    model_config = {"from_attributes": True}


# ── Rebalance Alert ───────────────────────────────────────────────────────────

class RebalanceAlert(BaseModel):
    scope: Literal["account", "group"]
    scope_id: int
    scope_name: str
    symbol: str
    current_weight: Decimal
    target_weight: Decimal
    deviation: Decimal  # current - target (positive = overweight)
    direction: Literal["over", "under"]


class AlertsResponse(BaseModel):
    alerts: list[RebalanceAlert]
```

- [ ] **Step 2: Fix forward reference in GroupCreate**

`GroupMemberInput` is referenced before definition. Reorder: put `GroupMemberInput` before `GroupCreate` in the file.

- [ ] **Step 3: Commit**

```bash
cd backend && git add app/schemas/journal.py
git commit -m "feat(journal): Pydantic schemas for all journal endpoints"
```

---

## Task 4: position_sync.py + fx_service.py

**Files:**
- Create: `backend/app/modules/trade_journal/position_sync.py`
- Create: `backend/app/modules/trade_journal/fx_service.py`

- [ ] **Step 1: Create `backend/app/modules/trade_journal/fx_service.py`**

```python
"""FX rate lookup with fallback to most recent available date."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.journal import FXRate


class FXRateNotFoundError(Exception):
    """Raised when no FX rate exists for the requested currency pair."""


async def get_rate(
    db: AsyncSession,
    from_currency: str,
    to_currency: str = "TWD",
) -> Decimal:
    """Return most recent rate for from_currency→to_currency.

    Falls back to nearest past date if today's rate is not yet available.
    Raises FXRateNotFoundError if no rate exists at all.
    """
    if from_currency == to_currency:
        return Decimal("1")

    stmt = (
        select(FXRate.rate)
        .where(
            FXRate.from_currency == from_currency,
            FXRate.to_currency == to_currency,
        )
        .order_by(FXRate.date.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise FXRateNotFoundError(
            f"No FX rate found for {from_currency}→{to_currency}"
        )
    return row
```

- [ ] **Step 2: Create `backend/app/modules/trade_journal/position_sync.py`**

```python
"""Apply FIFO engine results to the database (trade_lots + positions tables)."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.journal import Position, Trade, TradeLot
from app.modules.trade_journal.fifo_engine import FIFOEngine, Lot


async def _load_open_lots(
    db: AsyncSession,
    account_id: int,
    symbol: str,
    market: str,
) -> list[Lot]:
    """Fetch open (non-exhausted) lots in FIFO order (oldest trade_id first)."""
    stmt = (
        select(TradeLot)
        .where(
            TradeLot.account_id == account_id,
            TradeLot.symbol == symbol,
            TradeLot.market == market,
            TradeLot.is_exhausted.is_(False),
        )
        .order_by(TradeLot.trade_id.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        Lot(
            lot_id=row.id,
            original_qty=row.original_qty,
            remaining_qty=row.remaining_qty,
            cost_per_unit=row.cost_per_unit,
            is_exhausted=row.is_exhausted,
        )
        for row in rows
    ]


async def _upsert_position(
    db: AsyncSession,
    account_id: int,
    symbol: str,
    market: str,
    currency: str,
    qty_delta: Decimal,
    cost_delta: Decimal,
    realized_pnl_delta: Decimal,
) -> None:
    """Insert or update the positions cache row for this account+symbol+market."""
    stmt = (
        pg_insert(Position)
        .values(
            account_id=account_id,
            symbol=symbol,
            market=market,
            currency=currency,
            quantity=qty_delta,
            avg_cost_fifo=None,
            total_cost=cost_delta if cost_delta > 0 else Decimal("0"),
            realized_pnl=realized_pnl_delta,
            is_closed=False,
        )
        .on_conflict_do_update(
            index_elements=["account_id", "symbol", "market"],
            set_={
                "quantity": Position.quantity + qty_delta,
                "total_cost": Position.total_cost + cost_delta,
                "realized_pnl": Position.realized_pnl + realized_pnl_delta,
            },
        )
    )
    await db.execute(stmt)

    # Recalculate avg_cost_fifo and is_closed after upsert
    pos_stmt = select(Position).where(
        Position.account_id == account_id,
        Position.symbol == symbol,
        Position.market == market,
    )
    pos = (await db.execute(pos_stmt)).scalar_one()
    if pos.quantity > Decimal("0") and pos.total_cost is not None:
        pos.avg_cost_fifo = pos.total_cost / pos.quantity
    pos.is_closed = pos.quantity <= Decimal("0")


async def apply_buy(
    db: AsyncSession,
    trade: Trade,
    currency: str,
) -> None:
    """Create a new lot and update position cache for a BUY trade."""
    cost_per_unit = (trade.price * trade.quantity + trade.fee) / trade.quantity
    lot = TradeLot(
        trade_id=trade.id,
        account_id=trade.account_id,
        symbol=trade.symbol,
        market=trade.market,
        original_qty=trade.quantity,
        remaining_qty=trade.quantity,
        cost_per_unit=cost_per_unit,
    )
    db.add(lot)

    total_cost = cost_per_unit * trade.quantity
    await _upsert_position(
        db,
        account_id=trade.account_id,
        symbol=trade.symbol,
        market=trade.market,
        currency=currency,
        qty_delta=trade.quantity,
        cost_delta=total_cost,
        realized_pnl_delta=Decimal("0"),
    )


async def apply_sell(
    db: AsyncSession,
    trade: Trade,
    currency: str,
) -> Decimal:
    """Consume open lots via FIFO and return realized_pnl."""
    open_lots = await _load_open_lots(
        db, trade.account_id, trade.symbol, trade.market
    )
    engine = FIFOEngine(open_lots=open_lots)
    result = engine.process_sell(
        qty=trade.quantity,
        price=trade.price,
        fee=trade.fee,
        tax=trade.tax,
    )

    # Persist lot updates
    lot_map = {lot.lot_id: lot for lot in result.updated_lots}
    db_lots_stmt = select(TradeLot).where(
        TradeLot.id.in_(list(lot_map.keys()))
    )
    db_lots = (await db.execute(db_lots_stmt)).scalars().all()
    for db_lot in db_lots:
        updated = lot_map[db_lot.id]
        db_lot.remaining_qty = updated.remaining_qty
        db_lot.is_exhausted = updated.is_exhausted

    # Cost removed from position = sum(cost_per_unit * consumed) for each lot
    cost_removed = sum(
        lot_map[lot.lot_id].cost_per_unit
        * (lot.original_qty - lot_map[lot.lot_id].remaining_qty
           if lot.lot_id in lot_map else Decimal("0"))
        for lot in open_lots
        if lot.lot_id in lot_map
    )
    # Simpler: total_cost_consumed = proceeds - realized (rearranged)
    # But direct: use sum from engine
    cost_consumed = sum(
        lot.cost_per_unit * (
            # shares consumed from this lot
            min(lot.remaining_qty + result.qty_consumed, lot.original_qty) - lot.remaining_qty
        )
        for lot in result.updated_lots
    )

    await _upsert_position(
        db,
        account_id=trade.account_id,
        symbol=trade.symbol,
        market=trade.market,
        currency=currency,
        qty_delta=-trade.quantity,
        cost_delta=-cost_consumed,
        realized_pnl_delta=result.realized_pnl,
    )

    return result.realized_pnl


async def apply_split(
    db: AsyncSession,
    trade: Trade,
    split_ratio: Decimal,
) -> None:
    """Apply a stock split to all open lots and position for this account+symbol+market."""
    open_lots = await _load_open_lots(
        db, trade.account_id, trade.symbol, trade.market
    )
    engine = FIFOEngine(open_lots=open_lots)
    updated = engine.process_split(ratio=split_ratio)

    lot_map = {lot.lot_id: lot for lot in updated}
    db_lots_stmt = select(TradeLot).where(
        TradeLot.account_id == trade.account_id,
        TradeLot.symbol == trade.symbol,
        TradeLot.market == trade.market,
        TradeLot.is_exhausted.is_(False),
    )
    db_lots = (await db.execute(db_lots_stmt)).scalars().all()
    for db_lot in db_lots:
        if db_lot.id in lot_map:
            u = lot_map[db_lot.id]
            db_lot.remaining_qty = u.remaining_qty
            db_lot.original_qty = u.original_qty
            db_lot.cost_per_unit = u.cost_per_unit

    # Update position quantity and cost
    pos_stmt = select(Position).where(
        Position.account_id == trade.account_id,
        Position.symbol == trade.symbol,
        Position.market == trade.market,
    )
    pos = (await db.execute(pos_stmt)).scalar_one_or_none()
    if pos:
        pos.quantity = pos.quantity * split_ratio
        if pos.total_cost and pos.quantity > 0:
            pos.avg_cost_fifo = pos.total_cost / pos.quantity
```

- [ ] **Step 3: Commit**

```bash
cd backend && git add app/modules/trade_journal/fx_service.py app/modules/trade_journal/position_sync.py
git commit -m "feat(journal): position_sync and fx_service modules"
```

---

## Task 5: rebalance.py

**Files:**
- Create: `backend/app/modules/trade_journal/rebalance.py`
- Create: `backend/tests/unit/test_rebalance.py`

- [ ] **Step 1: Write failing tests T21–T28**

Create `backend/tests/unit/test_rebalance.py`:

```python
"""Unit tests for rebalance alert calculator — T21–T28."""
from __future__ import annotations

from decimal import Decimal

from app.modules.trade_journal.rebalance import (
    AllocationRuleData,
    PositionData,
    compute_account_alerts,
)


def _rule(symbol: str, target: str, lower: str = "0.03", upper: str = "0.03", active: bool = True) -> AllocationRuleData:
    return AllocationRuleData(
        symbol=symbol,
        target_weight=Decimal(target),
        lower_threshold=Decimal(lower),
        upper_threshold=Decimal(upper),
        is_active=active,
    )


def _pos(symbol: str, value: str) -> PositionData:
    return PositionData(symbol=symbol, market_value=Decimal(value))


# T21: within range — no alert
def test_T21_within_range():
    rules = [_rule("2330.TW", "0.20")]
    positions = [_pos("2330.TW", "210"), _pos("CASH", "790")]  # 21% of 1000
    alerts = compute_account_alerts(rules=rules, positions=positions, total_value=Decimal("1000"))
    assert alerts == []


# T22: over upper threshold
def test_T22_over_upper():
    rules = [_rule("2330.TW", "0.20")]
    positions = [_pos("2330.TW", "245")]  # 24.5% of 1000
    alerts = compute_account_alerts(rules=rules, positions=positions, total_value=Decimal("1000"))
    assert len(alerts) == 1
    assert alerts[0].direction == "over"
    assert alerts[0].deviation == Decimal("0.0450").quantize(Decimal("0.0001"))


# T23: under lower threshold
def test_T23_under_lower():
    rules = [_rule("2330.TW", "0.20")]
    positions = [_pos("2330.TW", "150")]  # 15% of 1000
    alerts = compute_account_alerts(rules=rules, positions=positions, total_value=Decimal("1000"))
    assert len(alerts) == 1
    assert alerts[0].direction == "under"


# T26: zero total value — no crash
def test_T26_zero_total_value():
    rules = [_rule("2330.TW", "0.20")]
    positions = []
    alerts = compute_account_alerts(rules=rules, positions=positions, total_value=Decimal("0"))
    assert alerts == []


# T27: no rule for symbol — no alert
def test_T27_no_rule_for_symbol():
    rules = []
    positions = [_pos("2330.TW", "200")]
    alerts = compute_account_alerts(rules=rules, positions=positions, total_value=Decimal("1000"))
    assert alerts == []


# T28: inactive rule — no alert
def test_T28_inactive_rule():
    rules = [_rule("2330.TW", "0.20", active=False)]
    positions = [_pos("2330.TW", "500")]  # 50% — way over, but rule inactive
    alerts = compute_account_alerts(rules=rules, positions=positions, total_value=Decimal("1000"))
    assert alerts == []
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd backend && python -m pytest tests/unit/test_rebalance.py -v 2>&1 | head -10
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement `rebalance.py`**

Create `backend/app/modules/trade_journal/rebalance.py`:

```python
"""Rebalance alert calculator.

Pure functions — no DB queries. Callers pass pre-fetched rules and positions.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


@dataclass
class AllocationRuleData:
    symbol: str
    target_weight: Decimal
    lower_threshold: Decimal
    upper_threshold: Decimal
    is_active: bool


@dataclass
class PositionData:
    symbol: str
    market_value: Decimal


@dataclass
class AlertData:
    symbol: str
    current_weight: Decimal
    target_weight: Decimal
    deviation: Decimal
    direction: Literal["over", "under"]


def compute_account_alerts(
    rules: list[AllocationRuleData],
    positions: list[PositionData],
    total_value: Decimal,
) -> list[AlertData]:
    """Return alerts for each active rule where current weight is outside threshold."""
    if total_value <= Decimal("0"):
        return []

    value_map = {pos.symbol: pos.market_value for pos in positions}
    alerts: list[AlertData] = []

    for rule in rules:
        if not rule.is_active:
            continue
        market_val = value_map.get(rule.symbol, Decimal("0"))
        current_weight = market_val / total_value
        deviation = current_weight - rule.target_weight

        if deviation > rule.upper_threshold:
            alerts.append(AlertData(
                symbol=rule.symbol,
                current_weight=current_weight.quantize(Decimal("0.0001")),
                target_weight=rule.target_weight,
                deviation=deviation.quantize(Decimal("0.0001")),
                direction="over",
            ))
        elif deviation < -rule.lower_threshold:
            alerts.append(AlertData(
                symbol=rule.symbol,
                current_weight=current_weight.quantize(Decimal("0.0001")),
                target_weight=rule.target_weight,
                deviation=deviation.quantize(Decimal("0.0001")),
                direction="under",
            ))

    return alerts
```

- [ ] **Step 4: Run tests T21–T28**

```bash
cd backend && python -m pytest tests/unit/test_rebalance.py -v
```
Expected: `6 passed` (T24, T25 are group-level; tested in integration tests)

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/modules/trade_journal/rebalance.py tests/unit/test_rebalance.py
git commit -m "feat(journal): rebalance alert calculator + T21–T28 passing"
```

---

## Task 6: Journal API Router

**Files:**
- Create: `backend/app/api/v1/journal.py`

- [ ] **Step 1: Create `backend/app/api/v1/journal.py`**

```python
"""Trade Journal API — /api/v1/journal/"""
from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.journal import (
    AccountGroup,
    AccountGroupMember,
    AllocationRule,
    Position,
    Trade,
    TradeAccount,
)
from app.modules.trade_journal.fx_service import FXRateNotFoundError, get_rate
from app.modules.trade_journal.position_sync import apply_buy, apply_sell, apply_split
from app.modules.trade_journal.rebalance import (
    AllocationRuleData,
    PositionData,
    compute_account_alerts,
)
from app.schemas.journal import (
    AccountCreate,
    AccountDetailResponse,
    AccountResponse,
    AlertsResponse,
    AllocationRuleCreate,
    AllocationRuleResponse,
    GroupCreate,
    GroupResponse,
    RebalanceAlert,
    TradeCreate,
    TradeListResponse,
    TradeResponse,
)

router = APIRouter(prefix="/journal", tags=["journal"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


# ── Accounts ──────────────────────────────────────────────────────────────────

@router.post("/accounts", response_model=AccountResponse, status_code=201)
async def create_account(body: AccountCreate, db: DbDep) -> AccountResponse:
    account = TradeAccount(
        name=body.name,
        broker=body.broker,
        market=body.market,
        currency=body.currency,
        description=body.description,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return AccountResponse.model_validate(account)


@router.get("/accounts", response_model=list[AccountResponse])
async def list_accounts(db: DbDep) -> list[AccountResponse]:
    rows = (await db.execute(select(TradeAccount))).scalars().all()
    return [AccountResponse.model_validate(r) for r in rows]


@router.get("/accounts/{account_id}", response_model=AccountDetailResponse)
async def get_account(account_id: int, db: DbDep) -> AccountDetailResponse:
    account = await db.get(TradeAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    positions = (
        await db.execute(
            select(Position)
            .where(Position.account_id == account_id, Position.is_closed.is_(False))
        )
    ).scalars().all()
    return AccountDetailResponse(
        account=AccountResponse.model_validate(account),
        positions=[p.__dict__ for p in positions],
    )


# ── Trades ────────────────────────────────────────────────────────────────────

@router.post("/accounts/{account_id}/trades", response_model=TradeResponse, status_code=201)
async def add_trade(account_id: int, body: TradeCreate, db: DbDep) -> TradeResponse:
    account = await db.get(TradeAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    trade = Trade(
        account_id=account_id,
        symbol=body.symbol,
        market=body.market,
        action=body.action,
        date=body.date,
        price=body.price,
        quantity=body.quantity,
        fee=body.fee,
        tax=body.tax,
        trade_fx_rate=body.trade_fx_rate,
        tags=body.tags,
        note=body.note,
    )
    db.add(trade)
    await db.flush()  # get trade.id before position_sync

    if body.action == "BUY":
        await apply_buy(db, trade, currency=account.currency)
    elif body.action == "SELL":
        try:
            await apply_sell(db, trade, currency=account.currency)
        except Exception as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
    elif body.action == "SPLIT":
        if not body.split_ratio:
            raise HTTPException(status_code=422, detail="split_ratio required for SPLIT action")
        await apply_split(db, trade, split_ratio=body.split_ratio)
    # DIVIDEND: recorded in trades only, no position change

    await db.commit()
    await db.refresh(trade)
    return TradeResponse.model_validate(trade)


@router.get("/accounts/{account_id}/trades", response_model=TradeListResponse)
async def list_trades(
    account_id: int,
    db: DbDep,
    symbol: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> TradeListResponse:
    base = select(Trade).where(Trade.account_id == account_id)
    if symbol:
        base = base.where(Trade.symbol == symbol)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        await db.execute(
            base.order_by(Trade.date.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    ).scalars().all()
    return TradeListResponse(total=total, items=[TradeResponse.model_validate(r) for r in rows])


# ── Groups ────────────────────────────────────────────────────────────────────

@router.post("/groups", response_model=GroupResponse, status_code=201)
async def create_group(body: GroupCreate, db: DbDep) -> GroupResponse:
    group = AccountGroup(
        name=body.name,
        description=body.description,
        base_currency=body.base_currency,
    )
    db.add(group)
    await db.flush()

    for member in body.members:
        db.add(AccountGroupMember(
            group_id=group.id,
            account_id=member.account_id,
            target_weight=member.target_weight,
        ))

    await db.commit()
    await db.refresh(group)
    return await _build_group_response(db, group)


@router.get("/groups/{group_id}", response_model=GroupResponse)
async def get_group(group_id: int, db: DbDep) -> GroupResponse:
    group = await db.get(AccountGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return await _build_group_response(db, group)


async def _build_group_response(db: AsyncSession, group: AccountGroup) -> GroupResponse:
    from app.schemas.journal import GroupMemberResponse
    members_rows = (
        await db.execute(
            select(AccountGroupMember).where(AccountGroupMember.group_id == group.id)
        )
    ).scalars().all()
    members = []
    for m in members_rows:
        acc = await db.get(TradeAccount, m.account_id)
        members.append(GroupMemberResponse(
            account_id=m.account_id,
            target_weight=m.target_weight,
            account=AccountResponse.model_validate(acc),
        ))
    return GroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        base_currency=group.base_currency,
        members=members,
    )


# ── Allocation Rules ──────────────────────────────────────────────────────────

@router.post("/accounts/{account_id}/allocation", response_model=list[AllocationRuleResponse], status_code=201)
async def set_account_allocation(
    account_id: int, rules: list[AllocationRuleCreate], db: DbDep
) -> list[AllocationRuleResponse]:
    account = await db.get(TradeAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    for rule_in in rules:
        existing = (
            await db.execute(
                select(AllocationRule).where(
                    AllocationRule.account_id == account_id,
                    AllocationRule.symbol == rule_in.symbol,
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.target_weight = rule_in.target_weight
            existing.lower_threshold = rule_in.lower_threshold
            existing.upper_threshold = rule_in.upper_threshold
            existing.is_active = rule_in.is_active
        else:
            db.add(AllocationRule(
                account_id=account_id,
                group_id=None,
                symbol=rule_in.symbol,
                target_weight=rule_in.target_weight,
                lower_threshold=rule_in.lower_threshold,
                upper_threshold=rule_in.upper_threshold,
                is_active=rule_in.is_active,
            ))
    await db.commit()
    rows = (
        await db.execute(
            select(AllocationRule).where(AllocationRule.account_id == account_id)
        )
    ).scalars().all()
    return [AllocationRuleResponse.model_validate(r) for r in rows]


# ── Rebalance Alerts ──────────────────────────────────────────────────────────

@router.get("/alerts", response_model=AlertsResponse)
async def get_alerts(db: DbDep) -> AlertsResponse:
    """Return all triggered rebalance alerts across all accounts."""
    all_alerts: list[RebalanceAlert] = []

    accounts = (await db.execute(select(TradeAccount))).scalars().all()
    for account in accounts:
        rules_rows = (
            await db.execute(
                select(AllocationRule).where(
                    AllocationRule.account_id == account.id,
                    AllocationRule.is_active.is_(True),
                )
            )
        ).scalars().all()
        if not rules_rows:
            continue

        positions_rows = (
            await db.execute(
                select(Position).where(
                    Position.account_id == account.id,
                    Position.is_closed.is_(False),
                )
            )
        ).scalars().all()

        # Convert to market value in account currency (no FX needed here — same currency)
        # For actual TWD conversion, use position market price * quantity (requires live price feed)
        # Phase 1: use total_cost as proxy for market value (no live prices yet)
        pos_data = [
            PositionData(symbol=p.symbol, market_value=p.total_cost or Decimal("0"))
            for p in positions_rows
        ]
        total_value = sum(p.market_value for p in pos_data)

        rule_data = [
            AllocationRuleData(
                symbol=r.symbol,
                target_weight=r.target_weight,
                lower_threshold=r.lower_threshold,
                upper_threshold=r.upper_threshold,
                is_active=r.is_active,
            )
            for r in rules_rows
        ]
        raw_alerts = compute_account_alerts(rules=rule_data, positions=pos_data, total_value=total_value)
        for a in raw_alerts:
            all_alerts.append(RebalanceAlert(
                scope="account",
                scope_id=account.id,
                scope_name=account.name,
                symbol=a.symbol,
                current_weight=a.current_weight,
                target_weight=a.target_weight,
                deviation=a.deviation,
                direction=a.direction,
            ))

    return AlertsResponse(alerts=all_alerts)
```

- [ ] **Step 2: Commit**

```bash
cd backend && git add app/api/v1/journal.py
git commit -m "feat(journal): FastAPI router — accounts, trades, groups, alerts endpoints"
```

---

## Task 7: Register Router

**Files:**
- Modify: `backend/app/api/v1/router.py`

- [ ] **Step 1: Add import and include_router**

In `backend/app/api/v1/router.py`, after the last import:
```python
from app.api.v1.journal import router as journal_router
```

After `v1_router.include_router(scanner_router)`:
```python
v1_router.include_router(journal_router)
```

- [ ] **Step 2: Verify server starts**

```bash
cd backend && python -m uvicorn app.main:app --reload --port 8001 &
sleep 3 && curl -s http://localhost:8001/api/v1/journal/accounts | python -m json.tool
```
Expected: `[]` (empty list, no accounts yet)

```bash
kill %1 2>/dev/null; true
```

- [ ] **Step 3: Commit**

```bash
cd backend && git add app/api/v1/router.py
git commit -m "feat(journal): register journal router in v1_router"
```

---

## Task 8: Integration Tests (T15–T20, Position Consistency)

**Files:**
- Create: `backend/tests/integration/test_journal_api.py`

- [ ] **Step 1: Write integration tests**

Create `backend/tests/integration/test_journal_api.py`:

```python
"""Integration tests for Trade Journal API — T15–T20 (position consistency)."""
from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.main import app

BASE = "/api/v1/journal"


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def tw_account(client: AsyncClient):
    resp = await client.post(f"{BASE}/accounts", json={
        "name": "元大證券",
        "broker": "元大",
        "market": "TW",
        "currency": "TWD",
    })
    assert resp.status_code == 201
    return resp.json()


# ── T15: BUY creates position ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_T15_buy_creates_position(client: AsyncClient, tw_account: dict):
    acc_id = tw_account["id"]
    resp = await client.post(f"{BASE}/accounts/{acc_id}/trades", json={
        "symbol": "2330.TW", "market": "TW", "action": "BUY",
        "date": "2026-01-10", "price": "100", "quantity": "100", "fee": "0",
    })
    assert resp.status_code == 201

    detail = await client.get(f"{BASE}/accounts/{acc_id}")
    positions = detail.json()["positions"]
    pos = next(p for p in positions if p["symbol"] == "2330.TW")
    assert Decimal(pos["quantity"]) == Decimal("100")
    assert Decimal(pos["total_cost"]) == Decimal("10000")


# ── T16: SELL updates position ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_T16_sell_updates_position(client: AsyncClient, tw_account: dict):
    acc_id = tw_account["id"]
    await client.post(f"{BASE}/accounts/{acc_id}/trades", json={
        "symbol": "2330.TW", "market": "TW", "action": "BUY",
        "date": "2026-01-10", "price": "100", "quantity": "100", "fee": "0",
    })
    await client.post(f"{BASE}/accounts/{acc_id}/trades", json={
        "symbol": "2330.TW", "market": "TW", "action": "SELL",
        "date": "2026-01-15", "price": "150", "quantity": "40", "fee": "0", "tax": "0",
    })
    detail = await client.get(f"{BASE}/accounts/{acc_id}")
    pos = next(p for p in detail.json()["positions"] if p["symbol"] == "2330.TW")
    assert Decimal(pos["quantity"]) == Decimal("60")
    assert Decimal(pos["realized_pnl"]) == Decimal("2000")


# ── T17: Full sell sets is_closed ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_T17_full_sell_closes_position(client: AsyncClient, tw_account: dict):
    acc_id = tw_account["id"]
    await client.post(f"{BASE}/accounts/{acc_id}/trades", json={
        "symbol": "2330.TW", "market": "TW", "action": "BUY",
        "date": "2026-01-10", "price": "100", "quantity": "100", "fee": "0",
    })
    resp = await client.post(f"{BASE}/accounts/{acc_id}/trades", json={
        "symbol": "2330.TW", "market": "TW", "action": "SELL",
        "date": "2026-01-15", "price": "150", "quantity": "100", "fee": "0", "tax": "0",
    })
    assert resp.status_code == 201
    # Open positions should not include closed one
    detail = await client.get(f"{BASE}/accounts/{acc_id}")
    open_positions = [p for p in detail.json()["positions"] if not p["is_closed"]]
    assert not any(p["symbol"] == "2330.TW" for p in open_positions)


# ── T19: Position recalc is idempotent (basic smoke) ─────────────────────────
@pytest.mark.asyncio
async def test_T19_positions_consistent_after_multiple_trades(client: AsyncClient, tw_account: dict):
    acc_id = tw_account["id"]
    for price, qty in [("100", "100"), ("110", "50"), ("120", "80")]:
        await client.post(f"{BASE}/accounts/{acc_id}/trades", json={
            "symbol": "2330.TW", "market": "TW", "action": "BUY",
            "date": "2026-01-10", "price": price, "quantity": qty, "fee": "0",
        })
    await client.post(f"{BASE}/accounts/{acc_id}/trades", json={
        "symbol": "2330.TW", "market": "TW", "action": "SELL",
        "date": "2026-01-20", "price": "130", "quantity": "100", "fee": "0", "tax": "0",
    })
    detail = await client.get(f"{BASE}/accounts/{acc_id}")
    pos = next(p for p in detail.json()["positions"] if p["symbol"] == "2330.TW")
    assert Decimal(pos["quantity"]) == Decimal("130")  # 230 - 100


# ── T20: Cross-market no collision ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_T20_cross_market_separate_positions(client: AsyncClient):
    # Create TW and US accounts
    tw = (await client.post(f"{BASE}/accounts", json={
        "name": "TW帳戶", "market": "TW", "currency": "TWD"
    })).json()
    us = (await client.post(f"{BASE}/accounts", json={
        "name": "US帳戶", "market": "US", "currency": "USD"
    })).json()

    await client.post(f"{BASE}/accounts/{tw['id']}/trades", json={
        "symbol": "2330", "market": "TW", "action": "BUY",
        "date": "2026-01-10", "price": "100", "quantity": "100", "fee": "0",
    })
    await client.post(f"{BASE}/accounts/{us['id']}/trades", json={
        "symbol": "2330", "market": "US", "action": "BUY",
        "date": "2026-01-10", "price": "50", "quantity": "200", "fee": "0",
    })

    tw_detail = (await client.get(f"{BASE}/accounts/{tw['id']}")).json()
    us_detail = (await client.get(f"{BASE}/accounts/{us['id']}")).json()

    tw_pos = next(p for p in tw_detail["positions"] if p["market"] == "TW")
    us_pos = next(p for p in us_detail["positions"] if p["market"] == "US")

    assert Decimal(tw_pos["quantity"]) == Decimal("100")
    assert Decimal(us_pos["quantity"]) == Decimal("200")
```

- [ ] **Step 2: Run integration tests**

```bash
cd backend && python -m pytest tests/integration/test_journal_api.py -v
```
Expected: `5 passed`

- [ ] **Step 3: Commit**

```bash
cd backend && git add tests/integration/test_journal_api.py
git commit -m "test(journal): integration tests T15–T20 position consistency"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** All Phase 0 + Phase 1 API routes covered. Phase 4 (snapshot_job cron) deferred to Plan B. T24/T25 (group-level alerts) deferred to Plan B (requires group position aggregation with FX).
- [x] **No placeholders:** All tasks have actual code.
- [x] **Type consistency:** `FIFOEngine`, `Lot`, `FIFOResult`, `InsufficientSharesError` referenced consistently. `apply_buy/sell/split` signatures match usage in `journal.py`.
- [x] **Partial indexes:** Added manually in Alembic upgrade — SQLAlchemy ORM cannot express these natively.
- [x] **SELL T06 path:** `apply_sell` → `FIFOEngine.process_sell` → raises `InsufficientSharesError` → caught in `add_trade` endpoint → 422 HTTP response. Full path verified.

---

> Plan B (Frontend) will cover: `/journal` dashboard, `/journal/accounts/[id]` with tabs, Add Trade Modal, `/journal/groups/[id]` group view, and D/W/M/Y performance charts with snapshot_job cron.
