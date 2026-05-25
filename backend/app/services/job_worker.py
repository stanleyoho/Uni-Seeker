from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.backtest_job import BacktestJob
from app.models.backtest_result import BacktestResultRecord
from app.models.price import StockPrice
from app.models.stock import Stock
from app.modules.backtester.engine import BacktestConfig, BacktestEngine
from app.modules.backtester.grid_search import GridSearchConfig, GridSearchEngine
from app.modules.backtester.portfolio_backtest import (
    PortfolioAllocation,
    PortfolioBacktestConfig,
    PortfolioBacktestEngine,
    RebalanceConfig,
)
from app.modules.strategy import create_default_registry
from app.modules.strategy.composite import CompositeStrategy
from app.obs.logging import get_logger
from app.services.job_queue import BacktestJobQueue

logger = get_logger(component="job_worker")

# Interval in seconds between queue polls when idle.
_POLL_INTERVAL = 2.0


class BacktestJobWorker:
    """Background worker that polls the job queue and executes backtest jobs.

    Usage::

        worker = BacktestJobWorker()
        await worker.start()   # spawns the polling loop as a background task
        ...
        await worker.stop()    # graceful shutdown
    """

    def __init__(self) -> None:
        self._queue = BacktestJobQueue()
        self._task: asyncio.Task[None] | None = None
        self._shutdown = asyncio.Event()

    async def start(self) -> None:
        """Start the background polling loop."""
        if self._task is not None:
            logger.warning("BacktestJobWorker is already running")
            return
        self._shutdown.clear()
        self._task = asyncio.create_task(self._poll_loop(), name="backtest-worker")
        logger.info("BacktestJobWorker started")

    async def stop(self) -> None:
        """Signal the worker to stop and wait for it to finish."""
        if self._task is None:
            return
        self._shutdown.set()
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        logger.info("BacktestJobWorker stopped")

    async def _poll_loop(self) -> None:
        """Continuously claim and execute jobs until shutdown is signalled."""
        logger.info("BacktestJobWorker poll loop running")
        while not self._shutdown.is_set():
            try:
                async with async_session() as db:
                    job = await self._queue.claim_next(db)
                    if job is not None:
                        await self._execute_job(job, db)
                        await db.commit()
                    else:
                        await db.commit()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected error in BacktestJobWorker poll loop")

            # Wait before next poll; break early on shutdown signal.
            try:
                await asyncio.wait_for(
                    self._shutdown.wait(),
                    timeout=_POLL_INTERVAL,
                )
                break  # shutdown was signalled
            except TimeoutError:
                pass  # normal — continue polling

    async def _execute_job(self, job: BacktestJob, db: AsyncSession) -> None:
        """Dispatch job to the appropriate backtest engine and persist results."""
        config = job.config_json or {}

        logger.info(
            "Executing job id=%s type=%s symbol=%s",
            job.id,
            job.job_type,
            job.symbol,
        )

        try:
            await self._queue.update_progress(db, job.id, 10)

            if job.job_type == "single":
                await self._run_single(job, config, db)
            elif job.job_type == "composite":
                await self._run_composite(job, config, db)
            elif job.job_type == "grid_search":
                await self._run_grid_search(job, config, db)
            elif job.job_type == "portfolio":
                await self._run_portfolio(job, config, db)
            else:
                raise ValueError(f"Unknown job_type: {job.job_type!r}")

            await self._queue.update_progress(db, job.id, 90)
            await self._queue.complete(
                db,
                job.id,
                result={
                    "job_type": job.job_type,
                    "symbol": job.symbol,
                    "status": "done",
                },
            )

        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.exception("Job id=%s failed", job.id)
            await self._queue.fail(db, job.id, error_msg)

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    async def _fetch_prices(
        self,
        db: AsyncSession,
        symbol: str,
    ) -> list[StockPrice]:
        """Fetch price history for *symbol* from the database."""
        stock_result = await db.execute(select(Stock).where(Stock.symbol == symbol))
        stock = stock_result.scalar_one_or_none()
        if stock is None:
            raise ValueError(f"Stock not found for symbol: {symbol!r}")

        price_result = await db.execute(
            select(StockPrice)
            .where(StockPrice.stock_id == stock.id)
            .order_by(StockPrice.date.asc())
        )
        prices = list(price_result.scalars().all())
        if not prices:
            raise ValueError(f"No price data for symbol: {symbol!r}")
        return prices

    def _build_bt_config(self, config: dict[str, Any]) -> BacktestConfig:
        """Build a BacktestConfig from a job's config_json dict."""
        return BacktestConfig(
            initial_capital=config.get("initial_capital", 1_000_000),
            position_size=config.get("position_size", 0.1),
            stop_loss=config.get("stop_loss"),
            take_profit=config.get("take_profit"),
        )

    def _save_result_record(
        self,
        db: AsyncSession,
        *,
        job_id: int,
        symbol: str,
        strategy_name: str,
        strategy_params: dict[str, Any],
        metrics: Any,
        equity_curve: list[Any],
        trade_log: list[Any],
        composite_mode: str | None = None,
    ) -> BacktestResultRecord:
        """Create a BacktestResultRecord and add it to the session."""
        record = BacktestResultRecord(
            job_id=job_id,
            symbol=symbol,
            strategy_name=strategy_name,
            strategy_params=strategy_params,
            metrics_json={
                "total_return": metrics.total_return,
                "annualized_return": metrics.annualized_return,
                "max_drawdown": metrics.max_drawdown,
                "sharpe_ratio": metrics.sharpe_ratio,
                "win_rate": metrics.win_rate,
                "total_trades": metrics.total_trades,
                "avg_holding_days": metrics.avg_holding_days,
                "profit_factor": metrics.profit_factor,
            },
            equity_curve=equity_curve,
            trade_log=trade_log,
            composite_mode=composite_mode,
            total_return=metrics.total_return,
            sharpe_ratio=metrics.sharpe_ratio,
            win_rate=metrics.win_rate,
        )
        db.add(record)
        return record

    # ------------------------------------------------------------------
    # Single strategy
    # ------------------------------------------------------------------

    async def _run_single(
        self,
        job: BacktestJob,
        config: dict[str, Any],
        db: AsyncSession,
    ) -> None:
        symbol = config["symbol"]
        prices = await self._fetch_prices(db, symbol)

        registry = create_default_registry()
        strategy = registry.get(
            config["strategy"],
            **config.get("params", {}),
        )

        bt_config = self._build_bt_config(config)
        await self._queue.update_progress(db, job.id, 50)

        result = BacktestEngine(bt_config).run(strategy, prices, symbol)

        self._save_result_record(
            db,
            job_id=job.id,
            symbol=symbol,
            strategy_name=config["strategy"],
            strategy_params=config.get("params", {}),
            metrics=result.metrics,
            equity_curve=result.equity_curve,
            trade_log=result.trade_log,
        )
        await db.flush()

    # ------------------------------------------------------------------
    # Composite strategy
    # ------------------------------------------------------------------

    async def _run_composite(
        self,
        job: BacktestJob,
        config: dict[str, Any],
        db: AsyncSession,
    ) -> None:
        symbol = config["symbol"]
        prices = await self._fetch_prices(db, symbol)

        registry = create_default_registry()
        strategy_params_map: dict[str, dict[str, Any]] = config.get("strategy_params", {})
        mode = config.get("mode", "all")

        sub_strategies = []
        for key in config["strategies"]:
            kwargs = strategy_params_map.get(key, {})
            sub_strategies.append(registry.get(key, **kwargs))

        if len(sub_strategies) == 1:
            strategy = sub_strategies[0]
        else:
            strategy = CompositeStrategy(strategies=sub_strategies, mode=mode)

        bt_config = self._build_bt_config(config)
        await self._queue.update_progress(db, job.id, 50)

        result = BacktestEngine(bt_config).run(strategy, prices, symbol)

        strategy_name = " + ".join(config["strategies"])
        self._save_result_record(
            db,
            job_id=job.id,
            symbol=symbol,
            strategy_name=strategy_name,
            strategy_params=strategy_params_map,
            metrics=result.metrics,
            equity_curve=result.equity_curve,
            trade_log=result.trade_log,
            composite_mode=mode,
        )
        await db.flush()

    # ------------------------------------------------------------------
    # Grid search
    # ------------------------------------------------------------------

    async def _run_grid_search(
        self,
        job: BacktestJob,
        config: dict[str, Any],
        db: AsyncSession,
    ) -> None:
        symbol = config["symbol"]
        prices = await self._fetch_prices(db, symbol)

        registry = create_default_registry()
        grid_config = GridSearchConfig(
            strategy_keys=config.get("strategies", []),
            param_grid=config.get("param_grid", {}),
            composite_mode=config.get("mode", "all"),
            initial_capital=config.get("initial_capital", 1_000_000),
            position_size=config.get("position_size", 0.95),
            stop_loss=config.get("stop_loss"),
            take_profit=config.get("take_profit"),
        )

        async def _progress_callback(pct: int) -> None:
            # Scale grid-search progress into 10-85 range
            scaled = 10 + int(pct * 0.75)
            await self._queue.update_progress(db, job.id, scaled)

        # GridSearchEngine.run is synchronous; wrap progress callback
        # to call async update_progress via the running event loop.
        asyncio.get_running_loop()

        _progress_tasks: set[asyncio.Future[None]] = set()

        def sync_progress(pct: int) -> None:
            task = asyncio.ensure_future(_progress_callback(pct))
            _progress_tasks.add(task)
            task.add_done_callback(_progress_tasks.discard)

        result = GridSearchEngine(registry).run(
            grid_config,
            prices,
            symbol,
            progress_callback=sync_progress,
        )

        # Save TOP 10 results as individual BacktestResultRecord rows
        top_results = result.results[:10]
        for item in top_results:
            record = BacktestResultRecord(
                job_id=job.id,
                symbol=symbol,
                strategy_name=item.name,
                strategy_params=item.params,
                metrics_json={
                    "total_return": item.total_return,
                    "annualized_return": item.annualized_return,
                    "max_drawdown": item.max_drawdown,
                    "sharpe_ratio": item.sharpe,
                    "win_rate": item.win_rate,
                    "total_trades": item.total_trades,
                    "profit_factor": item.profit_factor,
                    "wins": item.wins,
                    "losses": item.losses,
                },
                equity_curve={},
                trade_log={},
                composite_mode=grid_config.composite_mode,
                total_return=item.total_return,
                sharpe_ratio=item.sharpe,
                win_rate=item.win_rate,
            )
            db.add(record)
        await db.flush()

    # ------------------------------------------------------------------
    # Portfolio backtest
    # ------------------------------------------------------------------

    async def _run_portfolio(
        self,
        job: BacktestJob,
        config: dict[str, Any],
        db: AsyncSession,
    ) -> None:
        registry = create_default_registry()
        strategy_params_map: dict[str, dict[str, Any]] = config.get("strategy_params", {})

        # Build allocations and fetch prices for each symbol
        allocations: list[PortfolioAllocation] = []
        prices_map: dict[str, list[StockPrice]] = {}

        for alloc_cfg in config.get("allocations", []):
            sym = alloc_cfg["symbol"]
            strat_key = alloc_cfg.get("strategy", "rsi_oversold")
            kwargs = strategy_params_map.get(strat_key, {})
            strategy = registry.get(strat_key, **kwargs)

            allocations.append(
                PortfolioAllocation(
                    symbol=sym,
                    weight=alloc_cfg["weight"],
                    strategy=strategy,
                )
            )

            if sym not in prices_map:
                prices_map[sym] = await self._fetch_prices(db, sym)

        await self._queue.update_progress(db, job.id, 30)

        # Build rebalance config
        rebal_cfg = config.get("rebalance", {})
        rebalance = RebalanceConfig(
            mode=rebal_cfg.get("mode", "none"),
            period_days=rebal_cfg.get("period_days", 30),
            threshold_pct=rebal_cfg.get("threshold_pct", 5.0),
        )

        portfolio_config = PortfolioBacktestConfig(
            initial_capital=config.get("initial_capital", 1_000_000),
            fee_rate=config.get("fee_rate", 0.001425),
            tax_rate=config.get("tax_rate", 0.003),
            rebalance=rebalance,
        )

        await self._queue.update_progress(db, job.id, 50)

        result = PortfolioBacktestEngine(portfolio_config).run(
            allocations,
            prices_map,
        )

        # Save single result record for the portfolio
        pm = result.portfolio_metrics
        symbols_str = "+".join(a.symbol for a in allocations)
        strategies_str = "+".join(
            a.get("strategy", "rsi_oversold") for a in config.get("allocations", [])
        )

        record = BacktestResultRecord(
            job_id=job.id,
            symbol=symbols_str,
            strategy_name=f"Portfolio({strategies_str})",
            strategy_params={
                "allocations": config.get("allocations", []),
                "rebalance": rebal_cfg,
            },
            metrics_json=pm,
            equity_curve=result.portfolio_equity_curve,
            trade_log=[
                {
                    "date": t.date,
                    "symbol": t.symbol,
                    "action": t.action,
                    "price": t.price,
                    "shares": t.shares,
                    "reason": t.reason,
                }
                for t in result.trade_log
            ],
            composite_mode=None,
            total_return=pm.get("total_return", 0.0),
            sharpe_ratio=pm.get("sharpe_ratio", 0.0),
            win_rate=pm.get("win_rate", 0.0),
        )
        db.add(record)
        await db.flush()
