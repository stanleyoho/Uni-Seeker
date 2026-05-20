from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.backtest_job import BacktestJob
from app.models.backtest_result import BacktestResultRecord
from app.models.enums import Market, NotificationStatus, UserTier
from app.models.financial_metrics import FinancialMetrics
from app.models.financial_statement import FinancialStatement
from app.models.industry import Industry
from app.models.industry_metrics import IndustryMetrics
from app.models.journal import (
    AccountGroup,
    AccountGroupMember,
    AllocationRule,
    FXRate,
    PortfolioSnapshot,
    Position,
    Trade,
    TradeAccount,
    TradeLot,
)
from app.models.margin import MarginTrading
from app.models.notification import NotificationLog, NotificationRule
from app.models.portfolio_backtest import PortfolioBacktestRecord
from app.models.price import StockPrice
from app.models.price_estimate import PriceEstimate
from app.models.processed_webhook_event import ProcessedWebhookEvent
from app.models.revenue import MonthlyRevenue
from app.models.signal_scan import SignalScanRecord
from app.models.stock import Stock
from app.models.sync_state import SyncState
from app.models.user import User
from app.models.user_device import UserDevice
from app.models.valuation import StockValuation
from app.models.watchlist_item import WatchlistItem

# Portfolio Tracker (UNI-PORT-001) — ORM lives under app/db/models/portfolio/
# per design doc §5.5. Import here so the tables register on Base.metadata
# and Alembic autogenerate / create_all see them.
from app.db.models.portfolio import (  # noqa: E402, F401
    PortfolioAccount,
    PortfolioDividend,
    PortfolioLot,
    PortfolioPosition,
    PortfolioTrade,
)

__all__ = [
    "AccountGroup",
    "AccountGroupMember",
    "AllocationRule",
    "AuditLog",
    "BacktestJob",
    "BacktestResultRecord",
    "Base",
    "FinancialMetrics",
    "FinancialStatement",
    "FXRate",
    "Industry",
    "IndustryMetrics",
    "Market",
    "MarginTrading",
    "MonthlyRevenue",
    "NotificationLog",
    "NotificationRule",
    "NotificationStatus",
    "PortfolioBacktestRecord",
    "PortfolioSnapshot",
    "Position",
    "PriceEstimate",
    "ProcessedWebhookEvent",
    "SignalScanRecord",
    "Stock",
    "StockPrice",
    "StockValuation",
    "SyncState",
    "Trade",
    "TradeAccount",
    "TradeLot",
    "User",
    "UserDevice",
    "UserTier",
    "WatchlistItem",
]
