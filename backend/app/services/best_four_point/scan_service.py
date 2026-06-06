"""四大買賣點 daily universe scan + persistence (TW-only).

Pipeline (mirrors the low-base / scanner read-path, but write-once-per-day):

  1. Resolve the TW universe — active ``Stock`` rows in TW_TWSE / TW_TPEX.
  2. Batch-fetch every candidate's recent daily OHLCV in ONE query
     (``WHERE stock_id IN (...) ORDER BY stock_id, date`` — uses the
     existing ``ix_stock_prices_stock_id_date`` composite index, same trick
     the scanner / low-base endpoints use to avoid an N+1).
  3. Run the pure ``compute_best_four_point`` calculator per symbol.
  4. Persist *one row per scanned symbol* into ``signal_scans``
     (``SignalScanRecord``) for today's ``scan_date``, idempotently
     (delete-then-insert for the day so a re-run / catch-up overwrites
     cleanly rather than double-counting).

The HTTP endpoint (``GET /scanner/best-four-point``) only ever READS the
cached rows — it never triggers a universe scan, per the "compute on a
schedule, cache, API reads cached" decision.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select

from app.models.enums import Market
from app.models.price import StockPrice
from app.models.signal_scan import SignalScanRecord
from app.models.stock import Stock
from app.modules.best_four_point import OHLCVSeries, compute_best_four_point
from app.obs.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(component="best_four_point")

# Discriminator stored inside ``SignalScanRecord.signals_json`` so this
# feature's rows are distinguishable from any other future user of the
# shared ``signal_scans`` snapshot table.
SCAN_KIND = "best_four_point"

# TW markets only — this is a TW-only feature by spec.
_TW_MARKETS = (Market.TW_TWSE, Market.TW_TPEX)

# How many trailing trading days of OHLCV to pull per symbol. The
# calculator needs ≥ 7 bars; the bias-pivot looks back 5 spread values
# (each over a 6-day MA window), so ~30 days is comfortably enough while
# keeping the batch query small. Matches the scanner's lookback discipline.
PRICE_LOOKBACK = 30

# A symbol needs at least this many bars to produce a meaningful verdict
# (mirrors calculator.MIN_BARS). Symbols below this are skipped at scan
# time so the cache only holds rows we actually evaluated.
MIN_BARS = 7


async def run_best_four_point_scan(
    db: AsyncSession,
    *,
    scan_date: date | None = None,
) -> dict[str, int]:
    """Compute 四大買賣點 across the TW universe and persist today's results.

    Caller owns the transaction boundary — this function ``commit``s once at
    the end (the scheduler entrypoint opens/closes the session). Returns a
    summary dict: ``total_scanned`` / ``buy_signals`` / ``sell_signals`` /
    ``hold``.

    Idempotent for ``scan_date``: existing rows for the day are deleted
    before the fresh batch is inserted, so a catch-up re-run overwrites
    cleanly instead of duplicating.
    """
    if scan_date is None:
        scan_date = datetime.now(tz=ZoneInfo("Asia/Taipei")).date()

    # 1. TW universe — active TW listings only.
    candidate_rows = (
        await db.execute(
            select(Stock.id, Stock.symbol, Stock.name)
            .where(Stock.market.in_(_TW_MARKETS))
            .where(Stock.is_active.is_(True))
        )
    ).all()
    if not candidate_rows:
        logger.info("best_four_point_scan_no_universe", scan_date=str(scan_date))
        await _replace_day(db, scan_date, [])
        await db.commit()
        return {"total_scanned": 0, "buy_signals": 0, "sell_signals": 0, "hold": 0}

    id_to_meta: dict[int, tuple[str, str]] = {sid: (sym, name) for sid, sym, name in candidate_rows}

    # 2. Batch-fetch OHLCV for the whole candidate set in one query.
    prices_by_stock: dict[int, list[StockPrice]] = defaultdict(list)
    batched = await db.execute(
        select(StockPrice)
        .where(StockPrice.stock_id.in_(list(id_to_meta.keys())))
        .order_by(StockPrice.stock_id, StockPrice.date.asc())
    )
    for price in batched.scalars().all():
        prices_by_stock[price.stock_id].append(price)

    # 3. Compute per symbol.
    new_rows: list[SignalScanRecord] = []
    buy_count = sell_count = hold_count = 0

    for stock_id, (symbol, name) in id_to_meta.items():
        prices = prices_by_stock.get(stock_id, [])
        if len(prices) < MIN_BARS:
            continue
        recent = prices[-PRICE_LOOKBACK:]
        series = OHLCVSeries(
            opens=[float(p.open) for p in recent],
            highs=[float(p.high) for p in recent],
            lows=[float(p.low) for p in recent],
            closes=[float(p.close) for p in recent],
            volumes=[float(p.volume) for p in recent],
        )
        result = compute_best_four_point(series)

        if result.buy_points:
            buy_count += 1
        elif result.sell_points:
            sell_count += 1
        else:
            hold_count += 1

        payload: dict[str, Any] = {
            "kind": SCAN_KIND,
            "name": name or symbol,
            "verdict": result.verdict,
            "buy_points": result.buy_points,
            "sell_points": result.sell_points,
            "net_score": result.net_score,
            # Decimal-as-string per the app-wide numeric convention.
            "last_close": str(recent[-1].close),
        }
        new_rows.append(
            SignalScanRecord(
                symbol=symbol,
                scan_date=scan_date,
                signals_json=payload,
            )
        )

    # 4. Idempotent persist for the day.
    await _replace_day(db, scan_date, new_rows)
    await db.commit()

    summary = {
        "total_scanned": len(new_rows),
        "buy_signals": buy_count,
        "sell_signals": sell_count,
        "hold": hold_count,
    }
    logger.info("best_four_point_scan_done", scan_date=str(scan_date), **summary)
    return summary


async def _replace_day(
    db: AsyncSession,
    scan_date: date,
    new_rows: list[SignalScanRecord],
) -> None:
    """Delete this feature's existing rows for ``scan_date`` then insert fresh.

    Scoped to ``best_four_point`` rows only (other ``signal_scans`` users, if
    any, are untouched) by filtering on the JSON ``kind`` discriminator.
    ``signals_json["kind"]`` is matched in Python after a date-scoped fetch
    of ids — portable across SQLite (tests) and Postgres (prod) without
    relying on JSON-path operators that differ between the two.
    """
    existing = await db.execute(
        select(SignalScanRecord.id, SignalScanRecord.signals_json).where(
            SignalScanRecord.scan_date == scan_date
        )
    )
    stale_ids = [
        row_id
        for row_id, payload in existing.all()
        if isinstance(payload, dict) and payload.get("kind") == SCAN_KIND
    ]
    if stale_ids:
        await db.execute(delete(SignalScanRecord).where(SignalScanRecord.id.in_(stale_ids)))
    if new_rows:
        db.add_all(new_rows)


async def read_cached_scan(
    db: AsyncSession,
    *,
    scan_date: date | None = None,
) -> tuple[date | None, list[dict[str, Any]]]:
    """Read cached 四大買賣點 rows for ``scan_date`` (default: latest available).

    Returns ``(resolved_date, rows)`` where each row is the stored
    ``signals_json`` payload augmented with its ``symbol``. When no rows
    exist (fresh deploy / before first scan) returns ``(None, [])``.
    """
    if scan_date is None:
        # Latest scan_date that actually has best-four-point rows. Pull the
        # most-recent distinct dates and pick the first that contains our
        # kind (cheap: signal_scans is small — one batch per day).
        latest = await db.execute(
            select(SignalScanRecord.scan_date)
            .distinct()
            .order_by(SignalScanRecord.scan_date.desc())
        )
        candidate_dates = [d for (d,) in latest.all()]
        for d in candidate_dates:
            rows = await _read_day(db, d)
            if rows:
                return d, rows
        return None, []

    rows = await _read_day(db, scan_date)
    return (scan_date if rows else None), rows


async def _read_day(db: AsyncSession, scan_date: date) -> list[dict[str, Any]]:
    res = await db.execute(
        select(SignalScanRecord.symbol, SignalScanRecord.signals_json).where(
            SignalScanRecord.scan_date == scan_date
        )
    )
    rows: list[dict[str, Any]] = []
    for symbol, payload in res.all():
        if not isinstance(payload, dict) or payload.get("kind") != SCAN_KIND:
            continue
        rows.append({"symbol": symbol, **payload})
    return rows
