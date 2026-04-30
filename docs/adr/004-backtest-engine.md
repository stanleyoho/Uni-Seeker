# ADR-004: Backtest Engine Design

## Status: Accepted

## Context
Need a flexible backtesting system that supports single strategies, composite strategies, grid search, and portfolio backtesting.

## Decision
Layered architecture:
1. **Strategy Protocol**: `evaluate(closes) -> Signal(BUY/SELL/HOLD)`
2. **CompositeStrategy**: combines N strategies with ALL/ANY/MAJORITY voting
3. **BacktestEngine**: runs strategy on historical prices, tracks portfolio
4. **GridSearchEngine**: parameter optimization with composite scoring
5. **PortfolioBacktestEngine**: multi-stock with rebalancing
6. **Job Queue**: PostgreSQL-backed async job processing

## Key Design Decisions
- **Min trades filter (>=6)**: prevents overfitted strategies with 1-2 trades
- **Composite scoring**: Return 30% + Win Rate 25% + Sharpe 25% + Trade Frequency 20%
- **Stop-loss/take-profit**: checked before strategy signals each bar
- **Progress callback**: injectable for real-time UI updates during grid search

## Consequences
- Grid search is CPU-intensive (9,298 combos = ~10 min for one stock)
- Job queue needed for long-running searches
