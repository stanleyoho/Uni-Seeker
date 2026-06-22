"""Sync task: Taiwan stock listing (TaiwanStockInfo)."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Market
from app.models.industry import Industry
from app.models.stock import Stock
from app.models.sync_state import SyncState
from app.modules.finmind.market_provider import FinMindMarketProvider
from app.modules.sync_manager.rate_limiter import RateLimiter
from app.modules.sync_manager.tasks.base import SyncResult, SyncTask

logger = structlog.get_logger()


# FinMind TaiwanStockInfo ``type`` field → (Market, symbol suffix).
# Confirmed live values: "twse", "tpex", "emerging".
#   - "twse"     上市  → TW_TWSE, suffix ".TW"
#   - "tpex"     上櫃  → TW_TPEX, suffix ".TWO"
#   - "emerging" 興櫃  → NOT representable in the Market enum (no value for
#                        興櫃/pre-IPO). Returns None so the caller SKIPS the
#                        record rather than mislabelling it as TWSE.
# NB: the old code keyed off "OTC", which the feed never emits — that branch
# was dead, so every stock was mis-classified as TW_TWSE with a ".TW" suffix.
_TYPE_TO_MARKET: dict[str, tuple[Market, str]] = {
    "twse": (Market.TW_TWSE, ".TW"),
    "tpex": (Market.TW_TPEX, ".TWO"),
}


def _market_and_suffix(type_str: str) -> tuple[Market, str] | None:
    """Map a FinMind ``type`` value to (Market, symbol suffix).

    Returns ``None`` for values with no safe Market mapping (currently
    ``"emerging"`` 興櫃 and any unknown/blank value), signalling the caller
    to skip the record instead of guessing a market.
    """
    return _TYPE_TO_MARKET.get((type_str or "").strip().lower())


class StockInfoSyncTask(SyncTask):
    """Synchronise the stocks table from FinMind TaiwanStockInfo.

    This is a whole-market operation (one API call).  It upserts rows in
    the ``stocks`` table and creates missing industries.
    """

    dataset_name = "stock_info"

    async def run(
        self,
        db: AsyncSession,
        rate_limiter: RateLimiter,
        batch_size: int = 50,
    ) -> SyncResult:
        result = SyncResult(dataset=self.dataset_name)

        # -- acquire one API call permit ----------------------------------
        if not await rate_limiter.wait_and_acquire(timeout=30):
            result.stopped_reason = "rate_limit"
            return result

        try:
            provider = FinMindMarketProvider()
            raw = await provider.fetch_stock_info()
        except Exception as exc:
            logger.error("stock_info_fetch_error", error=str(exc))
            result.stopped_reason = "error"
            result.errors = 1
            result.error_details.append(str(exc))
            return result

        # -- build industry lookup ----------------------------------------
        industry_result = await db.execute(select(Industry))
        industry_map: dict[str, int] = {ind.name: ind.id for ind in industry_result.scalars().all()}
        industry_added = 0

        # -- snapshot existing stocks so we can diff per-row --------------
        existing_stocks_result = await db.execute(
            select(Stock.symbol, Stock.name, Stock.industry_id, Stock.market)
        )
        # symbol -> (name, industry_id, market_value)
        existing_map: dict[str, tuple[str, int | None, str]] = {
            row.symbol: (
                row.name,
                row.industry_id,
                row.market.value if hasattr(row.market, "value") else row.market,
            )
            for row in existing_stocks_result
        }

        # Per-bucket counters; surfaced in SyncResult.details for TG.
        added = 0
        renamed_examples: list[str] = []  # 收前 3 個改名範例
        renamed = 0
        industry_changed = 0
        market_changed = 0
        unchanged = 0
        skipped_emerging = 0  # 興櫃: no Market enum value, skipped on purpose

        # -- de-duplicate the feed by stock_id, newest ``date`` wins -------
        # The FinMind feed contains DUPLICATE stock_ids (155+ ids with >1
        # entry). Examples confirmed live:
        #   5450 → 寶聯通 (2020-06-03, stale/delisted) + 南良 (2026-06-21)
        #   6438 → tpex (old) + twse (new, uplisted)
        # Each duplicate maps to the same symbol, so without dedup the
        # upsert collides intra-run (last-writer-wins, order-dependent) and
        # the per-row diff flags a phantom "改名" on every run. Collapsing
        # to ONE record per stock_id (newest ISO date — string compare is
        # safe for YYYY-MM-DD) means one stock_id → one current listing →
        # one symbol → no collision → idempotent across runs.
        #
        # Dedup is by stock_id ALONE (not (stock_id, market)): a stock_id is
        # a single security whose current listing is its newest-dated entry,
        # even if it has uplisted from tpex to twse.
        deduped: dict[str, dict] = {}
        for record in raw:
            stock_id_str = (record.get("stock_id", "") or "").strip()
            stock_name = (record.get("stock_name", "") or "").strip()
            if not stock_id_str or not stock_name:
                continue
            rec_date = record.get("date", "") or ""
            prior = deduped.get(stock_id_str)
            # Keep the record with the newest date. ">=" is deliberate so a
            # later record with an equal/blank date does not silently lose;
            # for genuinely distinct dates the strictly-newest one wins.
            if prior is None or rec_date >= (prior.get("date", "") or ""):
                deduped[stock_id_str] = record

        # -- process the deduped records ----------------------------------
        # After dedup there is exactly one record per stock_id, so each
        # symbol is written at most once per run: the upsert cannot collide.
        for stock_id_str, record in deduped.items():
            stock_name = (record.get("stock_name", "") or "").strip()
            industry_name: str = record.get("industry_category", "") or ""
            market_raw: str = record.get("type", "")

            mapping = _market_and_suffix(market_raw)
            if mapping is None:
                # 興櫃 / unknown type — no safe Market value, skip rather than
                # mislabel. Counted so the human reconciliation has a number.
                skipped_emerging += 1
                continue
            market, suffix = mapping

            # Ensure industry exists
            industry_id: int | None = None
            if industry_name:
                if industry_name not in industry_map:
                    new_ind = Industry(name=industry_name)
                    db.add(new_ind)
                    await db.flush()
                    industry_map[industry_name] = new_ind.id
                    industry_added += 1
                industry_id = industry_map[industry_name]

            symbol = f"{stock_id_str}{suffix}"

            # Diff against the snapshot of existing DB rows to classify this
            # row. Because each symbol is unique in the deduped set, the
            # snapshot is consistent for the whole run (no intra-run write
            # ever invalidates another row's comparison), so reading from a
            # pre-loop snapshot is correct here — unlike the reverted fix,
            # which diffed duplicate rows that shared a symbol.
            prior = existing_map.get(symbol)
            if prior is None:
                added += 1
            else:
                prior_name, prior_industry_id, prior_market = prior
                changed_anything = False
                if prior_name != stock_name:
                    renamed += 1
                    if len(renamed_examples) < 3:
                        renamed_examples.append(f"{stock_id_str} {prior_name}→{stock_name}")
                    changed_anything = True
                if prior_industry_id != industry_id:
                    industry_changed += 1
                    changed_anything = True
                if prior_market != market.value:
                    market_changed += 1
                    changed_anything = True
                if not changed_anything:
                    unchanged += 1

            # Upsert stock
            stmt = pg_insert(Stock).values(
                symbol=symbol,
                name=stock_name,
                market=market,
                industry_id=industry_id,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol"],
                set_={
                    "name": stmt.excluded.name,
                    "market": stmt.excluded.market,
                    "industry_id": stmt.excluded.industry_id,
                },
            )
            await db.execute(stmt)
            result.records_synced += 1

        result.stocks_processed = result.records_synced

        # Surface the diff breakdown for the TG notification.
        result.details = {
            "新增": added,
            "改名": renamed,
            "換產業": industry_changed,
            "上下市": market_changed,
            "未變動": unchanged,
            "新增產業類別": industry_added,
            "略過興櫃": skipped_emerging,
        }
        if renamed_examples:
            result.extras["改名範例"] = renamed_examples

        # -- update sync state (global row, stock_id IS NULL) ---------------
        now = datetime.now(UTC)
        existing = await db.execute(
            select(SyncState).where(
                SyncState.dataset == self.dataset_name,
                SyncState.stock_id.is_(None),
            )
        )
        row = existing.scalar_one_or_none()
        if row:
            row.last_synced_date = datetime.now(tz=ZoneInfo("Asia/Taipei")).date()
            row.last_run_at = now
            row.status = "completed"
            row.records_synced = result.records_synced
            row.error_message = None
        else:
            db.add(
                SyncState(
                    dataset=self.dataset_name,
                    stock_id=None,
                    last_synced_date=datetime.now(tz=ZoneInfo("Asia/Taipei")).date(),
                    last_run_at=now,
                    status="completed",
                    records_synced=result.records_synced,
                    error_message=None,
                )
            )
        await db.commit()

        result.stopped_reason = "completed"
        logger.info(
            "stock_info_sync_completed",
            records=result.records_synced,
        )
        return result
