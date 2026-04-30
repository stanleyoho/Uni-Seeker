# ADR-003: Backend Architecture — FastAPI + SQLAlchemy Async + PostgreSQL

## Status: Accepted

## Context
Need a Python backend for financial data processing, backtesting, and API serving.

## Decision
Use FastAPI with async SQLAlchemy and PostgreSQL.

## Rationale
- FastAPI: automatic OpenAPI docs, async support, Pydantic validation
- SQLAlchemy async: non-blocking DB queries under load
- PostgreSQL: JSONB for flexible data, robust indexing, FOR UPDATE SKIP LOCKED for job queue
- Modular architecture: each domain (strategy, backtester, scanner) is an independent module

## Key Patterns
- Strategy Protocol: any class with `evaluate(closes) -> Signal` is a valid strategy
- Registry pattern: StrategyRegistry and IndicatorRegistry for plugin-like extensibility
- Computation/IO separation: engines take data as params, never query DB directly

## Consequences
- async/await adds complexity to testing
- PostgreSQL required (not SQLite compatible for production)
