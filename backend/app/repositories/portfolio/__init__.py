"""Portfolio Tracker repositories (Phase 1 / UNI-PORT-001).

CRUD-only layer over `app.db.models.portfolio.*`. Per design spec §5.3 +
§11 R3, repos MUST NOT contain business logic (P&L calc, FIFO, tier
check). Those belong to the service / domain layer.

Structural user isolation: every query that touches a user's data
takes a non-optional `user_id` parameter and applies it as a `WHERE`
clause (directly or via JOIN). There is no method on these repos that
can return one user's row to another user.
"""

# Eagerly load `app.models` so that the package fully initialises before
# any of our `app.db.models.portfolio.*` leaf imports trigger
# `app.models.base`. Without this, a fresh import that enters via the
# repositories path races with `app.models/__init__.py`'s own portfolio
# re-export and explodes with a circular ImportError.
from app import models as _app_models
from app.repositories.portfolio.account_repo import PortfolioAccountRepo
from app.repositories.portfolio.dividend_repo import PortfolioDividendRepo
from app.repositories.portfolio.lot_repo import PortfolioLotRepo
from app.repositories.portfolio.position_repo import PortfolioPositionRepo
from app.repositories.portfolio.price_lookup_repo import PriceLookupRepo
from app.repositories.portfolio.snapshot_repo import HoldingsSnapshotRepo
from app.repositories.portfolio.trade_repo import PortfolioTradeRepo

__all__ = [
    "HoldingsSnapshotRepo",
    "PortfolioAccountRepo",
    "PortfolioDividendRepo",
    "PortfolioLotRepo",
    "PortfolioPositionRepo",
    "PortfolioTradeRepo",
    "PriceLookupRepo",
]
