# Cross-package model packages are imported for side effect only — their
# __init__ files run the SQLAlchemy class definitions that register tables
# on ``Base.metadata`` (consumed by alembic env.py and metadata.create_all).
#
# We deliberately do NOT use ``from X import Y`` here. That syntax forces
# Python to bind the attribute Y on the (partially-loaded) submodule X,
# which triggers an ImportError when this __init__ is re-entered during a
# cross-package cycle. The canonical trigger:
#
#   scripts/seed_e2e_data.py:54  →  import app.db.models
#   app.db.models.__init__:5     →  from app.db.models import alerts
#   alerts.__init__:3            →  from .alert_rule import AlertRule
#   alert_rule.py:26             →  from app.models.base import Base
#                                      (which runs this __init__)
#   this file (old):             →  from app.db.models.alerts import AlertRule
#                                      → alerts is mid-load, AlertRule not yet
#                                        bound → ImportError.
#
# ``import X`` (no name lookup) is safe under that partial-load condition —
# Python returns the partial module and we never touch a not-yet-defined
# attribute. The class registrations on Base.metadata still happen because
# the import side effect runs each module body exactly once.
#
# Public re-exports remain via ``app.models.<submodule_dotted_path>`` for
# anyone who wants them; the cross-package names are not listed in
# ``__all__`` (verified). No external caller imports these from app.models
# (grep verified: 0 hits across app/ and tests/).

# User-defined Alert Rules (UNI-ALERT-001).
import app.db.models.alerts

# 13F Holdings Tracker (UNI-F13-001) — ORM lives under
# app/db/models/institutional/ per design doc §6.5.
import app.db.models.institutional

# Portfolio Tracker (UNI-PORT-001) — ORM lives under app/db/models/portfolio/
# per design doc §5.5.
import app.db.models.portfolio
from app.models.audit_log import AuditLog
from app.models.backtest_job import BacktestJob
from app.models.backtest_result import BacktestResultRecord
from app.models.base import Base
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

__all__ = [
    "AccountGroup",
    "AccountGroupMember",
    "AllocationRule",
    "AuditLog",
    "BacktestJob",
    "BacktestResultRecord",
    "Base",
    "FXRate",
    "FinancialMetrics",
    "FinancialStatement",
    "Industry",
    "IndustryMetrics",
    "MarginTrading",
    "Market",
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
