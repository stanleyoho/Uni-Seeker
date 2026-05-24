"""Portfolio Tracker services (Phase 1 / UNI-PORT-001 Batch C).

Service layer: orchestrates `app.repositories.portfolio.*` (CRUD) +
`app.modules.portfolio.*` (pure domain logic) behind a transaction
boundary. Spec §5.2 / §7 / §9 / §11.

Anti-coupling guarantees (spec §11):
- R2: no raw SQL here — every DB touch goes through a repo.
- R3 (mirror): no FIFO / P&L math here — every computation goes through
  a domain module.
- R5: services receive an `AsyncSession` injected by the API layer; they
  never create their own DB session.

Tier enforcement (spec §9):
- Endpoint guard (`tier_guard(...)` dependency) is the first line.
- Service-level assertions in `account_service` / `trade_service` are
  the second line — they raise domain exceptions (`TierLimitExceeded`)
  that the API layer converts to `HTTPException(403)`. This guarantees
  that even a programmer who forgets the `Depends(...)` cannot create
  data over a tier quota.
"""

from app.services.portfolio.account_service import PortfolioAccountService
from app.services.portfolio.analytics_service import AnalyticsService
from app.services.portfolio.dividend_service import (
    PortfolioDividendNotFound,
    PortfolioDividendService,
)
from app.services.portfolio.exceptions import (
    PortfolioAccountNotFound,
    PortfolioServiceError,
    PortfolioTradeNotFound,
    TierFeatureUnavailable,
    TierLimitExceeded,
)
from app.services.portfolio.export_service import CsvExportService
from app.services.portfolio.import_service import CsvImportService
from app.services.portfolio.position_service import (
    PortfolioPositionService,
    PositionWithPnL,
)
from app.services.portfolio.summary_service import PortfolioSummaryService
from app.services.portfolio.tax_report_service import TaxReportService
from app.services.portfolio.trade_service import PortfolioTradeService

__all__ = [
    "AnalyticsService",
    "CsvExportService",
    "CsvImportService",
    "PortfolioAccountNotFound",
    "PortfolioAccountService",
    "PortfolioDividendNotFound",
    "PortfolioDividendService",
    "PortfolioPositionService",
    "PortfolioServiceError",
    "PortfolioSummaryService",
    "PortfolioTradeNotFound",
    "PortfolioTradeService",
    "PositionWithPnL",
    "TaxReportService",
    "TierFeatureUnavailable",
    "TierLimitExceeded",
]
