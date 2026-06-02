"""ETF arbitrage (premium / discount) monitoring module.

Models the twetf.com core feature ported into Uni-Seeker:

    premium% = (market_price - estimated_nav) / estimated_nav * 100

Five-level sentiment taxonomy:
- 過熱  (premium >  +1.0)   🔴
- 溢價  (+0.1  .. +1.0)     🟠
- 平價  (-0.1  .. +0.1)     ⚪
- 折價  (-1.0  .. -0.1)     🔵
- 深折  (premium <  -1.0)   🟣
"""

from app.modules.etf_arbitrage.classifier import (
    SENTIMENT_LEVELS,
    classify_etf_type,
    classify_sentiment,
)
from app.modules.etf_arbitrage.service import (
    ETFArbitrageRow,
    ETFArbitrageService,
    ETFArbitrageStats,
)

__all__ = [
    "SENTIMENT_LEVELS",
    "ETFArbitrageRow",
    "ETFArbitrageService",
    "ETFArbitrageStats",
    "classify_etf_type",
    "classify_sentiment",
]
