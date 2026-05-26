"""Enhanced-mode coverage for /api/v1/low-base/* endpoints.

Basic-mode happy path lives in ``test_low_base_api.py``; the enhanced
branch (``?enhanced=true``) requires both
``FinMindInstitutionalProvider.fetch_institutional`` and
``SignalScanner.scan_stock`` to be patched out so no live network or
external dataset access happens. These tests target the missing
``_aggregate_5d_net`` / ``_scanner_score_to_100`` / per-stock enhancement
branches in ``app/api/v1/low_base.py``.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.low_base import _aggregate_5d_net, _scanner_score_to_100
from app.models.enums import Market
from app.models.price import StockPrice
from app.models.stock import Stock

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession


async def _mk_stock_with_history(
    db: AsyncSession,
    symbol: str,
    name: str,
    num_days: int,
    base_close: float = 100.0,
) -> Stock:
    s = Stock(symbol=symbol, name=name, market=Market.TW_TWSE)
    db.add(s)
    await db.commit()
    await db.refresh(s)

    base_date = date(2026, 5, 1)
    for i in range(num_days):
        c = base_close + (i % 7) * 0.5
        p = StockPrice(
            stock_id=s.id,
            date=base_date - timedelta(days=num_days - i - 1),
            open=Decimal(str(c)),
            high=Decimal(str(c)),
            low=Decimal(str(c)),
            close=Decimal(str(c)),
            change=Decimal("0"),
            volume=100_000,
        )
        db.add(p)
    await db.commit()
    return s


def _institutional_records() -> list[dict[str, object]]:
    """Six FinMind-shape rows covering each category we map.

    The mapping in ``_CATEGORY_MAP`` collapses Dealer_self + Dealer_Hedging
    into ``dealer``. We include two of each category × two days so we
    can verify summation as well.
    """
    return [
        # Day 1
        {"name": "Foreign_Investor", "buy": 1000, "sell": 200},  # +800
        {"name": "Investment_Trust", "buy": 500, "sell": 100},  # +400
        {"name": "Dealer_self", "buy": 300, "sell": 100},  # +200
        # Day 2
        {"name": "Foreign_Investor", "buy": 700, "sell": 300},  # +400
        {"name": "Dealer_Hedging", "buy": 200, "sell": 50},  # +150
        # Unknown category — must be silently ignored.
        {"name": "AlienOverlord", "buy": 99999, "sell": 0},
    ]


def _fake_scanner_signal(score: float = 0.4) -> MagicMock:
    """Stand-in for ``StockSignal`` returned by SignalScanner.scan_stock."""
    sig = MagicMock()
    sig.score = score
    sig.composite_action = "BUY"
    sig.signals = []
    return sig


# ──────────────────────────────────────────────────────────────────────
# Helper / pure-function units
# ──────────────────────────────────────────────────────────────────────


def test_aggregate_5d_net_sums_per_category() -> None:
    nets = _aggregate_5d_net(_institutional_records())
    # Foreign: 800 + 400 = 1200
    assert nets["foreign_net"] == 1200.0
    # Trust: 400
    assert nets["trust_net"] == 400.0
    # Dealer (self + hedging): 200 + 150 = 350
    assert nets["dealer_net"] == 350.0


def test_aggregate_5d_net_handles_empty_input() -> None:
    nets = _aggregate_5d_net([])
    assert nets == {"foreign_net": 0.0, "trust_net": 0.0, "dealer_net": 0.0}


def test_aggregate_5d_net_skips_unknown_category() -> None:
    """A row whose ``name`` is not in _CATEGORY_MAP contributes nothing."""
    nets = _aggregate_5d_net(
        [
            {"name": "TheVoid", "buy": 999, "sell": 0},
            {"name": "Foreign_Investor", "buy": 100, "sell": 50},
        ]
    )
    assert nets["foreign_net"] == 50.0
    assert nets["trust_net"] == 0.0
    assert nets["dealer_net"] == 0.0


def test_scanner_score_to_100_maps_endpoints_and_midpoint() -> None:
    # -1 → 0, 0 → 50, +1 → 100, and values outside the [-1, 1] range
    # are clamped.
    assert _scanner_score_to_100(-1.0) == 0.0
    assert _scanner_score_to_100(0.0) == 50.0
    assert _scanner_score_to_100(1.0) == 100.0
    assert _scanner_score_to_100(-2.0) == 0.0  # clamped low
    assert _scanner_score_to_100(2.0) == 100.0  # clamped high


# ──────────────────────────────────────────────────────────────────────
# GET /low-base/{symbol}?enhanced=true
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_score_enhanced_uses_mocked_institutional_and_scanner(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Enhanced single-stock endpoint exercises both providers when mocked."""
    await _mk_stock_with_history(db_session, "2330", "TSMC", num_days=60)

    inst_mock = MagicMock()
    inst_mock.fetch_institutional = AsyncMock(return_value=_institutional_records())

    with (
        patch(
            "app.api.v1.low_base.FinMindInstitutionalProvider",
            return_value=inst_mock,
        ),
        patch(
            "app.api.v1.low_base.SignalScanner.scan_stock",
            return_value=_fake_scanner_signal(score=0.4),
        ),
    ):
        resp = await client.get("/api/v1/low-base/2330?enhanced=true")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["symbol"] == "2330"
    # Institutional + technical sub-score is present in enhanced mode.
    assert "institutional_technical_score" in data
    # The provider was awaited exactly once with the cleaned symbol.
    assert inst_mock.fetch_institutional.await_count == 1
    args, kwargs = inst_mock.fetch_institutional.await_args
    assert kwargs["stock_id"] == "2330"


@pytest.mark.asyncio
async def test_get_score_enhanced_recovers_from_provider_exception(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A FinMind error must not 5xx the endpoint — it's logged and skipped."""
    await _mk_stock_with_history(db_session, "2454", "MediaTek", num_days=60)

    inst_mock = MagicMock()
    inst_mock.fetch_institutional = AsyncMock(side_effect=RuntimeError("boom"))

    with (
        patch(
            "app.api.v1.low_base.FinMindInstitutionalProvider",
            return_value=inst_mock,
        ),
        # Scanner raises too — both failures must be swallowed.
        patch(
            "app.api.v1.low_base.SignalScanner.scan_stock",
            side_effect=RuntimeError("nope"),
        ),
    ):
        resp = await client.get("/api/v1/low-base/2454?enhanced=true")

    assert resp.status_code == 200, resp.text
    # Endpoint still returns a payload (basic score path).
    assert resp.json()["symbol"] == "2454"


# ──────────────────────────────────────────────────────────────────────
# GET /low-base/scan?enhanced=true
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scan_enhanced_with_mocked_providers(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Scan endpoint loops every eligible stock through enhanced enrichment."""
    await _mk_stock_with_history(db_session, "2330", "TSMC", num_days=60)
    await _mk_stock_with_history(db_session, "2454", "MediaTek", num_days=60)

    inst_mock = MagicMock()
    inst_mock.fetch_institutional = AsyncMock(return_value=_institutional_records())

    with (
        patch(
            "app.api.v1.low_base.FinMindInstitutionalProvider",
            return_value=inst_mock,
        ),
        patch(
            "app.api.v1.low_base.SignalScanner.scan_stock",
            return_value=_fake_scanner_signal(score=0.2),
        ),
    ):
        resp = await client.get("/api/v1/low-base/scan?limit=10&min_data_days=60&enhanced=true")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_scanned"] == 2
    # fetch_institutional called once per stock.
    assert inst_mock.fetch_institutional.await_count == 2


@pytest.mark.asyncio
async def test_scan_enhanced_handles_provider_returning_empty_list(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """When the provider yields an empty list the enhanced fields are simply
    omitted and the endpoint still returns 200.
    """
    await _mk_stock_with_history(db_session, "2330", "TSMC", num_days=60)

    inst_mock = MagicMock()
    inst_mock.fetch_institutional = AsyncMock(return_value=[])

    with (
        patch(
            "app.api.v1.low_base.FinMindInstitutionalProvider",
            return_value=inst_mock,
        ),
        patch(
            "app.api.v1.low_base.SignalScanner.scan_stock",
            return_value=_fake_scanner_signal(score=0.0),
        ),
    ):
        resp = await client.get("/api/v1/low-base/scan?limit=10&min_data_days=60&enhanced=true")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_scanned"] == 1


@pytest.mark.asyncio
async def test_scan_enhanced_resilient_to_per_stock_failures(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A provider failure for one stock must not abort the whole scan."""
    await _mk_stock_with_history(db_session, "2330", "TSMC", num_days=60)
    await _mk_stock_with_history(db_session, "2454", "MediaTek", num_days=60)

    inst_mock = MagicMock()
    inst_mock.fetch_institutional = AsyncMock(
        side_effect=[RuntimeError("rate limit"), _institutional_records()]
    )

    with (
        patch(
            "app.api.v1.low_base.FinMindInstitutionalProvider",
            return_value=inst_mock,
        ),
        # Scanner blows up for every call — both must be swallowed.
        patch(
            "app.api.v1.low_base.SignalScanner.scan_stock",
            side_effect=RuntimeError("nope"),
        ),
    ):
        resp = await client.get("/api/v1/low-base/scan?limit=10&min_data_days=60&enhanced=true")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_scanned"] == 2
