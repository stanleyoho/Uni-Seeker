"""Integration tests for POST /api/v1/watchlist/indicators — A2 live panel v1.

Covers the end-to-end HTTP path:
  N01 happy path — price from feed + computed RSI/MA/cross/pct, 4-dp strings
  N02 unauthenticated → 401
  N03 unknown symbol still returns a row, all numeric fields None
  N04 no price feed for a known symbol → price/change None, history-derived
      indicators still present
  N05 request-order preserved + duplicates deduped
  N06 validation — empty symbols list → 422 (Pydantic min_length)
  N07 Decimal-as-string contract on the wire (no floats leak through)
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.holdings._deps import get_live_price_fetcher
from app.auth import create_access_token
from app.models.enums import Market, UserTier
from app.models.price import StockPrice
from app.models.stock import Stock
from app.models.user import User
from app.modules.portfolio.live_price_fetcher import PriceQuote


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.email)}"}


async def _mk_user(db: AsyncSession, email: str, tier: UserTier = UserTier.FREE) -> User:
    u = User(email=email, hashed_password="x" * 60, username=email.split("@")[0])
    u.tier = tier
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _mk_stock(db: AsyncSession, symbol: str, name: str) -> Stock:
    s = Stock(symbol=symbol, name=name, market=Market.TW_TWSE)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


async def _seed_closes(db: AsyncSession, stock_id: int, closes: list[float]) -> None:
    """Seed `closes` as consecutive daily bars (ascending dates)."""
    base = date(2026, 1, 1)
    for i, c in enumerate(closes):
        db.add(
            StockPrice(
                stock_id=stock_id,
                date=base + timedelta(days=i),
                open=Decimal(str(c)),
                high=Decimal(str(c)),
                low=Decimal(str(c)),
                close=Decimal(str(c)),
                volume=1_000_000,
            )
        )
    await db.commit()


class _MockLivePriceFetcher:
    """In-memory fetcher mirroring the LivePriceFetcher Protocol."""

    def __init__(self, quotes: dict[str, tuple[Decimal, Decimal]] | None = None) -> None:
        self._quotes = quotes or {}

    async def fetch_quotes(self, stock_ids: list[str]) -> dict[str, PriceQuote]:
        out: dict[str, PriceQuote] = {}
        for sid in stock_ids:
            if sid not in self._quotes:
                continue
            last, prev = self._quotes[sid]
            out[sid] = PriceQuote(
                stock_id=sid,
                last_price=last,
                prev_close=prev,
                as_of=datetime(2026, 1, 31, tzinfo=UTC),
            )
        return out


def _client_app(client: AsyncClient):  # type: ignore[no-untyped-def]
    return client._transport.app  # type: ignore[attr-defined]


@pytest.fixture
def mock_fetcher(client: AsyncClient):  # type: ignore[no-untyped-def]
    """Install a deterministic price fetcher on the test app; clean up after."""
    app = _client_app(client)

    def _setup(quotes: dict[str, tuple[Decimal, Decimal]]) -> None:
        app.dependency_overrides[get_live_price_fetcher] = lambda: _MockLivePriceFetcher(quotes)

    yield _setup
    app.dependency_overrides.pop(get_live_price_fetcher, None)


# ─────────────────────────────────────────────────────────────────────
# N01 — happy path
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_N01_happy_path(client: AsyncClient, db_session: AsyncSession, mock_fetcher) -> None:
    user = await _mk_user(db_session, "n1@x.tw")
    stock = await _mk_stock(db_session, "2330.TW", "台積電")
    # Rising series → golden cross, price above long MA.
    await _seed_closes(db_session, stock.id, [100.0 + i for i in range(40)])
    mock_fetcher({"2330.TW": (Decimal("150"), Decimal("140"))})

    r = await client.post(
        "/api/v1/watchlist/indicators",
        json={"symbols": ["2330.TW"]},
        headers=_auth(user),
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    row = items[0]
    assert row["symbol"] == "2330.TW"
    assert row["last_price"] == "150.0000"
    assert row["prev_close"] == "140.0000"
    assert row["change"] == "10.0000"
    assert row["ma_cross"] == "golden"
    assert row["rsi"] == "100.0000"
    # pct_from_ma_long present and positive (price 150 well above MA20).
    assert row["pct_from_ma_long"] is not None
    assert Decimal(row["pct_from_ma_long"]) > 0


# ─────────────────────────────────────────────────────────────────────
# N02 — unauthenticated
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_N02_requires_auth(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/watchlist/indicators",
        json={"symbols": ["2330.TW"]},
    )
    assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────
# N03 — unknown symbol → row with all-None numerics
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_N03_unknown_symbol_returns_none_row(
    client: AsyncClient, db_session: AsyncSession, mock_fetcher
) -> None:
    user = await _mk_user(db_session, "n3@x.tw")
    mock_fetcher({})  # no quotes at all

    r = await client.post(
        "/api/v1/watchlist/indicators",
        json={"symbols": ["NOPE"]},
        headers=_auth(user),
    )
    assert r.status_code == 200, r.text
    row = r.json()["items"][0]
    assert row["symbol"] == "NOPE"
    assert row["last_price"] is None
    assert row["rsi"] is None
    assert row["ma_cross"] is None


# ─────────────────────────────────────────────────────────────────────
# N04 — known symbol w/ history but NO price feed
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_N04_history_without_feed(
    client: AsyncClient, db_session: AsyncSession, mock_fetcher
) -> None:
    user = await _mk_user(db_session, "n4@x.tw")
    stock = await _mk_stock(db_session, "AAPL", "Apple")
    await _seed_closes(db_session, stock.id, [100.0 + i for i in range(30)])
    mock_fetcher({})  # feed returns nothing for AAPL

    r = await client.post(
        "/api/v1/watchlist/indicators",
        json={"symbols": ["AAPL"]},
        headers=_auth(user),
    )
    assert r.status_code == 200, r.text
    row = r.json()["items"][0]
    # No feed → price falls back to latest close (129), MA context still there.
    assert row["last_price"] == "129.0000"
    assert row["ma_cross"] == "golden"
    assert row["rsi"] is not None


# ─────────────────────────────────────────────────────────────────────
# N05 — request order preserved + dedupe
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_N05_order_preserved_and_deduped(
    client: AsyncClient, db_session: AsyncSession, mock_fetcher
) -> None:
    user = await _mk_user(db_session, "n5@x.tw")
    await _mk_stock(db_session, "AAA", "Aaa")
    await _mk_stock(db_session, "BBB", "Bbb")
    mock_fetcher({})

    r = await client.post(
        "/api/v1/watchlist/indicators",
        # lowercase + duplicate to exercise normalisation + dedupe.
        json={"symbols": ["bbb", "AAA", "BBB"]},
        headers=_auth(user),
    )
    assert r.status_code == 200, r.text
    symbols = [row["symbol"] for row in r.json()["items"]]
    assert symbols == ["BBB", "AAA"]


# ─────────────────────────────────────────────────────────────────────
# N06 — empty list rejected by Pydantic
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_N06_empty_symbols_422(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "n6@x.tw")
    r = await client.post(
        "/api/v1/watchlist/indicators",
        json={"symbols": []},
        headers=_auth(user),
    )
    assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────
# N07 — Decimal-as-string contract (no raw floats on the wire)
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_N07_decimal_as_string(
    client: AsyncClient, db_session: AsyncSession, mock_fetcher
) -> None:
    user = await _mk_user(db_session, "n7@x.tw")
    stock = await _mk_stock(db_session, "2454.TW", "聯發科")
    await _seed_closes(db_session, stock.id, [50.0 + i for i in range(25)])
    mock_fetcher({"2454.TW": (Decimal("80"), Decimal("75"))})

    r = await client.post(
        "/api/v1/watchlist/indicators",
        json={"symbols": ["2454.TW"]},
        headers=_auth(user),
    )
    assert r.status_code == 200, r.text
    row = r.json()["items"][0]
    # Every populated numeric must be a string, never a JSON number.
    for key in ("last_price", "prev_close", "change", "change_percent", "rsi"):
        assert isinstance(row[key], str), f"{key} should be string, got {type(row[key])}"
