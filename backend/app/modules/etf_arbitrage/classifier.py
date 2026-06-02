"""Pure classification helpers for ETF arbitrage rows.

Two independent concerns:

1. **Sentiment**  — bucket premium% into a 5-level taxonomy that the
   frontend renders as 🔴 / 🟠 / ⚪ / 🔵 / 🟣 lights (the same palette
   W4-B is rolling out across the rest of the app).
2. **ETF type**  — coarse classification of the ETF based on its name.
   Used by the `type` query filter on the listing endpoint. Heuristic
   only — Taiwan ETF naming is fairly disciplined so substring matching
   gets us most of the way there; a stocks table column can replace it
   once the master data set is enriched.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

# Public constants ────────────────────────────────────────────────────

# Order matters — the frontend uses this list verbatim in its 雷達 widget
# (left-to-right: 過熱 / 溢價 / 平價 / 折價 / 深折).
SENTIMENT_LEVELS: Final[tuple[str, ...]] = (
    "過熱",
    "溢價",
    "平價",
    "折價",
    "深折",
)

# All known ETF "type" tags exposed by the API. Mirror this in the
# frontend chip bar so the two stay in sync.
ETF_TYPES: Final[tuple[str, ...]] = (
    "股票型",
    "主動式",
    "債券型",
    "槓桿反向",
)

# Thresholds in *percent* (i.e. 1.0 means 1 %). Tuned to match the
# twetf.com colour breakdown shown in the reference screenshot.
_OVERHEAT_THRESHOLD: Final[Decimal] = Decimal("1.0")
_PREMIUM_THRESHOLD: Final[Decimal] = Decimal("0.1")
_DISCOUNT_THRESHOLD: Final[Decimal] = Decimal("-0.1")
_DEEP_DISCOUNT_THRESHOLD: Final[Decimal] = Decimal("-1.0")


def classify_sentiment(premium_percent: Decimal | float | str) -> str:
    """Return one of the 5 sentiment buckets for the given premium%.

    Tolerant of the Decimal-as-string convention used across the
    backend — accepts Decimal, float, or string. Non-numeric input
    raises ``ValueError`` rather than silently mapping to 平價, because
    that would conceal upstream data bugs.
    """
    pct = Decimal(str(premium_percent))

    if pct > _OVERHEAT_THRESHOLD:
        return "過熱"
    if pct >= _PREMIUM_THRESHOLD:
        return "溢價"
    if pct > _DISCOUNT_THRESHOLD:
        return "平價"
    if pct >= _DEEP_DISCOUNT_THRESHOLD:
        return "折價"
    return "深折"


# ETF-type name substring → canonical type tag. Order is intentional:
# 槓桿反向 must be checked BEFORE 股票型 because most leveraged ETFs
# also contain a stock-style underlying name (e.g. 富邦台灣加權正2 → 槓桿反向
# trumps 股票型). 主動式 likewise must precede 股票型.
_TYPE_RULES: Final[tuple[tuple[tuple[str, ...], str], ...]] = (
    (("正2", "反1", "槓桿", "反向", "L2", "S1", "正二", "反一"), "槓桿反向"),
    (("主動", "Active"), "主動式"),
    (("債", "公債", "投等", "投資等級", "高收", "ESG債", "bond", "Bond", "BOND"), "債券型"),
)


def classify_etf_type(name: str | None) -> str:
    """Return one of ``ETF_TYPES`` for the given ETF display name.

    The fallback is ``"股票型"`` because the vast majority of Taiwan ETFs
    by count are equity ETFs. Returning a non-None default keeps the
    frontend filter chips honest (no "unknown" bucket).
    """
    if not name:
        return "股票型"
    for needles, type_tag in _TYPE_RULES:
        if any(needle in name for needle in needles):
            return type_tag
    return "股票型"
