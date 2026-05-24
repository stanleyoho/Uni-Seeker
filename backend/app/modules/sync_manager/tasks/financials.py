"""Sync task: Financial Statements (income, balance sheet, cash flow)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.financial_statement import FinancialStatement
from app.models.stock import Stock
from app.models.sync_state import SyncState
from app.modules.finmind.client import FinMindClient, FinMindRateLimitError
from app.modules.sync_manager.rate_limiter import RateLimiter
from app.modules.sync_manager.tasks.base import SyncResult, SyncTask

logger = structlog.get_logger()

# FinMind dataset → statement_type mapping
_DATASET_MAP: list[tuple[str, str]] = [
    ("TaiwanStockFinancialStatements", "income"),
    ("TaiwanStockBalanceSheet", "balance"),
    ("TaiwanStockCashFlowsStatement", "cashflow"),
]


def _pivot_eav(records: list[dict]) -> dict[str, dict[str, float]]:
    """Group EAV records by date, return {date: {type: value}}."""
    result: dict[str, dict[str, float]] = {}
    for r in records:
        d = r.get("date", "")
        t = r.get("type", "")
        v = r.get("value")
        if d and t and v is not None:
            result.setdefault(d, {})[t] = float(v)
    return result


def _date_to_period(date_str: str) -> tuple[str, int, int] | None:
    """Convert FinMind date to (period, fiscal_year, fiscal_quarter)."""
    try:
        d = date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None
    month = d.month
    if month == 3:
        q = 1
    elif month == 6:
        q = 2
    elif month == 9:
        q = 3
    elif month == 12:
        q = 4
    else:
        return None
    return f"{d.year}-Q{q}", d.year, q


class FinancialsSyncTask(SyncTask):
    """Synchronise quarterly financial statements for all tracked stocks."""

    dataset_name = "financials"

    async def run(
        self,
        db: AsyncSession,
        rate_limiter: RateLimiter,
        batch_size: int = 50,
    ) -> SyncResult:
        result = SyncResult(dataset=self.dataset_name)
        today = datetime.now(tz=ZoneInfo("Asia/Taipei")).date()

        # -- load active stocks -------------------------------------------
        stocks_q = await db.execute(
            select(Stock).where(Stock.is_active.is_(True)).order_by(Stock.id)
        )
        stocks = stocks_q.scalars().all()

        if not stocks:
            result.stopped_reason = "completed"
            return result

        # -- sync state map -----------------------------------------------
        sync_q = await db.execute(select(SyncState).where(SyncState.dataset == self.dataset_name))
        sync_map: dict[int | None, SyncState] = {s.stock_id: s for s in sync_q.scalars().all()}

        client = FinMindClient(
            token=settings.finmind_api_token,
            base_url=settings.finmind_api_url,
        )

        processed = 0
        for stock in stocks:
            state = sync_map.get(stock.id)
            if state and state.last_synced_date and state.last_synced_date >= today:
                continue

            start_date = (
                (state.last_synced_date + timedelta(days=1))
                if state and state.last_synced_date
                else date(2020, 1, 1)
            )
            data_id = stock.symbol.replace(".TW", "")

            max_date = start_date

            # Fetch all three statement types for this stock
            for finmind_dataset, stmt_type in _DATASET_MAP:
                if not await rate_limiter.wait_and_acquire(timeout=30):
                    result.stopped_reason = "rate_limit"
                    break

                try:
                    raw = await client.fetch(
                        dataset=finmind_dataset,
                        data_id=data_id,
                        start_date=start_date.isoformat(),
                        end_date=today.isoformat(),
                    )
                except FinMindRateLimitError:
                    result.stopped_reason = "rate_limit"
                    break
                except Exception as exc:
                    logger.error(
                        "financials_sync_fetch_error",
                        stock=stock.symbol,
                        dataset=finmind_dataset,
                        error=str(exc),
                    )
                    result.errors += 1
                    result.error_details.append(f"{stock.symbol}/{stmt_type}: {exc}")
                    continue

                pivoted = _pivot_eav(raw)

                for date_str, data_dict in pivoted.items():
                    period_info = _date_to_period(date_str)
                    if period_info is None:
                        continue
                    period, fiscal_year, fiscal_quarter = period_info

                    try:
                        row_date = date.fromisoformat(date_str)
                    except (ValueError, TypeError):
                        continue

                    stmt = pg_insert(FinancialStatement).values(
                        stock_id=stock.id,
                        period=period,
                        statement_type=stmt_type,
                        data=data_dict,
                        is_cumulative=True,
                        fiscal_year=fiscal_year,
                        fiscal_quarter=fiscal_quarter,
                    )
                    stmt = stmt.on_conflict_do_update(
                        constraint="uq_fin_stmt_stock_period_type",
                        set_={
                            "data": stmt.excluded.data,
                            "is_cumulative": stmt.excluded.is_cumulative,
                            "fiscal_year": stmt.excluded.fiscal_year,
                            "fiscal_quarter": stmt.excluded.fiscal_quarter,
                        },
                    )
                    await db.execute(stmt)
                    result.records_synced += 1

                    if row_date > max_date:
                        max_date = row_date

            # Break out of stock loop if rate-limited during dataset fetch
            if result.stopped_reason == "rate_limit":
                break

            # -- update sync state ----------------------------------------
            now = datetime.now(UTC)
            sync_stmt = pg_insert(SyncState).values(
                dataset=self.dataset_name,
                stock_id=stock.id,
                last_synced_date=max_date,
                last_run_at=now,
                status="completed",
                records_synced=result.records_synced,
                error_message=None,
            )
            sync_stmt = sync_stmt.on_conflict_do_update(
                constraint="uq_sync_state_with_stock",
                set_={
                    "last_synced_date": max_date,
                    "last_run_at": now,
                    "status": "completed",
                    "records_synced": sync_stmt.excluded.records_synced,
                    "error_message": None,
                },
            )
            await db.execute(sync_stmt)
            await db.commit()

            processed += 1
            result.stocks_processed = processed

            if processed % batch_size == 0 and rate_limiter.remaining < 5:
                result.stopped_reason = "rate_limit"
                break

        if result.stopped_reason is None:
            result.stopped_reason = "completed"

        logger.info(
            "financials_sync_finished",
            stocks_processed=result.stocks_processed,
            records=result.records_synced,
            stopped=result.stopped_reason,
        )
        return result
