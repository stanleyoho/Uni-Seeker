"""Unit tests for `app.modules.strategy.chip` — 5 chip-data (籌碼面)
strategies that consume institutional / margin / shareholding records.

All strategies are stateful (history-accumulating) and pure-compute;
no DB or network. Each test exercises the full BUY / SELL / HOLD
decision matrix + boundary conditions.
"""

from __future__ import annotations

from app.modules.strategy.chip import (
    ForeignTrustSyncStrategy,
    InstitutionalFollowStrategy,
    MarginDivergenceStrategy,
    MarginOverleverageStrategy,
    OwnershipConcentrationStrategy,
)

# ── InstitutionalFollowStrategy ─────────────────────────────────────────


def test_inst_follow_insufficient_history_holds() -> None:
    s = InstitutionalFollowStrategy(days=3)
    sig = s.evaluate(
        [100.0], institutional=[{"name": "Foreign_Investor", "buy": 1000, "sell": 500}]
    )
    assert sig.action == "HOLD"
    assert "Insufficient" in sig.reason


def test_inst_follow_three_consecutive_net_buy_returns_buy() -> None:
    s = InstitutionalFollowStrategy(days=3)
    for _ in range(3):
        sig = s.evaluate(
            [100.0],
            institutional=[
                {"name": "Foreign_Investor", "buy": 1500, "sell": 500},
            ],
        )
    assert sig.action == "BUY"
    assert "net-buy" in sig.reason


def test_inst_follow_three_consecutive_net_sell_returns_sell() -> None:
    s = InstitutionalFollowStrategy(days=3)
    for _ in range(3):
        sig = s.evaluate(
            [100.0],
            institutional=[
                {"name": "Foreign_Investor", "buy": 500, "sell": 1500},
            ],
        )
    assert sig.action == "SELL"
    assert "net-sell" in sig.reason


def test_inst_follow_no_consecutive_trend_holds() -> None:
    s = InstitutionalFollowStrategy(days=3)
    # Mix of buy and sell — no consecutive direction
    for buy, sell in [(1500, 500), (500, 1500), (1500, 500)]:
        sig = s.evaluate(
            [100.0],
            institutional=[
                {"name": "Foreign_Investor", "buy": buy, "sell": sell},
            ],
        )
    assert sig.action == "HOLD"
    assert "no consecutive trend" in sig.reason


def test_inst_follow_investor_type_mismatch_treats_as_zero() -> None:
    """When the investor_type isn't in the data, net_buy defaults to 0."""
    s = InstitutionalFollowStrategy(days=3, investor_type="Investment_Trust")
    for _ in range(3):
        # Only Foreign_Investor data — Trust net is 0
        sig = s.evaluate(
            [100.0],
            institutional=[
                {"name": "Foreign_Investor", "buy": 5000, "sell": 0},
            ],
        )
    # net_buy=0 doesn't satisfy `> 0` nor `< 0` → HOLD
    assert sig.action == "HOLD"


# ── MarginDivergenceStrategy ────────────────────────────────────────────


def test_margin_divergence_insufficient_history_holds() -> None:
    s = MarginDivergenceStrategy(lookback=5)
    sig = s.evaluate(
        [100.0],
        margin=[
            {
                "MarginPurchaseTodayBalance": 1000,
                "ShortSaleTodayBalance": 500,
            }
        ],
    )
    assert sig.action == "HOLD"


def test_margin_divergence_contrarian_buy_on_retail_bearish() -> None:
    """Margin shrinking + short rising → retail bearish → contrarian BUY."""
    s = MarginDivergenceStrategy(lookback=5)
    # 6 data points: margin going DOWN, short going UP
    for m, sh in [(1000, 100), (900, 200), (800, 300), (700, 400), (600, 500), (500, 600)]:
        sig = s.evaluate(
            [100.0],
            margin=[
                {
                    "MarginPurchaseTodayBalance": m,
                    "ShortSaleTodayBalance": sh,
                }
            ],
        )
    assert sig.action == "BUY"
    assert "retail bearish" in sig.reason


def test_margin_divergence_fomo_sell_on_extreme_margin_surge() -> None:
    """Margin surging 2x more than abs(short trend) → retail FOMO → SELL."""
    s = MarginDivergenceStrategy(lookback=5)
    # margin +1000, short +50 → 1000 > 50*2
    for m, sh in [(1000, 100), (1200, 110), (1400, 120), (1600, 130), (1800, 140), (2000, 150)]:
        sig = s.evaluate(
            [100.0],
            margin=[
                {
                    "MarginPurchaseTodayBalance": m,
                    "ShortSaleTodayBalance": sh,
                }
            ],
        )
    assert sig.action == "SELL"
    assert "FOMO" in sig.reason


def test_margin_divergence_no_signal_holds() -> None:
    s = MarginDivergenceStrategy(lookback=5)
    # Both stable
    for _ in range(6):
        sig = s.evaluate(
            [100.0],
            margin=[
                {
                    "MarginPurchaseTodayBalance": 1000,
                    "ShortSaleTodayBalance": 500,
                }
            ],
        )
    assert sig.action == "HOLD"


# ── ForeignTrustSyncStrategy ────────────────────────────────────────────


def test_foreign_trust_sync_both_buying_returns_buy() -> None:
    s = ForeignTrustSyncStrategy(min_net_buy=0)
    sig = s.evaluate(
        [100.0],
        institutional=[
            {"name": "Foreign_Investor", "buy": 5000, "sell": 1000},
            {"name": "Investment_Trust", "buy": 3000, "sell": 500},
        ],
    )
    assert sig.action == "BUY"
    assert "sync buy" in sig.reason


def test_foreign_trust_sync_both_selling_returns_sell() -> None:
    s = ForeignTrustSyncStrategy(min_net_buy=0)
    sig = s.evaluate(
        [100.0],
        institutional=[
            {"name": "Foreign_Investor", "buy": 1000, "sell": 5000},
            {"name": "Investment_Trust", "buy": 500, "sell": 3000},
        ],
    )
    assert sig.action == "SELL"
    assert "sync sell" in sig.reason


def test_foreign_trust_sync_mixed_directions_holds() -> None:
    s = ForeignTrustSyncStrategy(min_net_buy=0)
    sig = s.evaluate(
        [100.0],
        institutional=[
            {"name": "Foreign_Investor", "buy": 5000, "sell": 1000},  # net buy
            {"name": "Investment_Trust", "buy": 500, "sell": 3000},  # net sell
        ],
    )
    assert sig.action == "HOLD"


def test_foreign_trust_sync_threshold_filters_small_moves() -> None:
    s = ForeignTrustSyncStrategy(min_net_buy=10_000)
    sig = s.evaluate(
        [100.0],
        institutional=[
            {"name": "Foreign_Investor", "buy": 1000, "sell": 500},  # +500 < 10_000
            {"name": "Investment_Trust", "buy": 1000, "sell": 500},
        ],
    )
    assert sig.action == "HOLD"


# ── OwnershipConcentrationStrategy ──────────────────────────────────────


def test_ownership_concentration_insufficient_history_holds() -> None:
    s = OwnershipConcentrationStrategy(days=5)
    sig = s.evaluate([100.0], shareholding=[{"ForeignInvestmentSharesRatio": 30.0}])
    assert sig.action == "HOLD"


def test_ownership_concentration_increasing_returns_buy() -> None:
    s = OwnershipConcentrationStrategy(days=3)
    # 4 data points, all monotonically increasing
    for ratio in [25.0, 26.0, 27.5, 30.0]:
        sig = s.evaluate([100.0], shareholding=[{"ForeignInvestmentSharesRatio": ratio}])
    assert sig.action == "BUY"
    assert "increasing" in sig.reason


def test_ownership_concentration_decreasing_returns_sell() -> None:
    s = OwnershipConcentrationStrategy(days=3)
    for ratio in [30.0, 28.0, 26.0, 24.0]:
        sig = s.evaluate([100.0], shareholding=[{"ForeignInvestmentSharesRatio": ratio}])
    assert sig.action == "SELL"
    assert "decreasing" in sig.reason


def test_ownership_concentration_no_trend_holds() -> None:
    s = OwnershipConcentrationStrategy(days=3)
    for ratio in [25.0, 26.0, 25.5, 26.5]:
        sig = s.evaluate([100.0], shareholding=[{"ForeignInvestmentSharesRatio": ratio}])
    assert sig.action == "HOLD"
    assert "no clear trend" in sig.reason


# ── MarginOverleverageStrategy ──────────────────────────────────────────


def test_margin_overleverage_no_data_holds() -> None:
    s = MarginOverleverageStrategy()
    sig = s.evaluate([100.0], margin=[])
    assert sig.action == "HOLD"
    assert "No margin utilization data" in sig.reason


def test_margin_overleverage_zero_limit_holds() -> None:
    """limit=0 → no utilization calc → HOLD."""
    s = MarginOverleverageStrategy()
    sig = s.evaluate(
        [100.0],
        margin=[
            {
                "MarginPurchaseTodayBalance": 500,
                "MarginPurchaseLimit": 0,
            }
        ],
    )
    assert sig.action == "HOLD"


def test_margin_overleverage_high_util_returns_sell() -> None:
    s = MarginOverleverageStrategy(sell_threshold=80.0)
    # util = 900/1000 * 100 = 90%
    sig = s.evaluate(
        [100.0],
        margin=[
            {
                "MarginPurchaseTodayBalance": 900,
                "MarginPurchaseLimit": 1000,
            }
        ],
    )
    assert sig.action == "SELL"
    assert "overleveraged" in sig.reason


def test_margin_overleverage_low_util_returns_buy() -> None:
    s = MarginOverleverageStrategy(buy_threshold=30.0)
    # util = 100/1000 * 100 = 10%
    sig = s.evaluate(
        [100.0],
        margin=[
            {
                "MarginPurchaseTodayBalance": 100,
                "MarginPurchaseLimit": 1000,
            }
        ],
    )
    assert sig.action == "BUY"
    assert "deleveraged" in sig.reason


def test_margin_overleverage_neutral_range_holds() -> None:
    s = MarginOverleverageStrategy(sell_threshold=80, buy_threshold=30)
    # util = 500/1000 * 100 = 50% — between 30 and 80
    sig = s.evaluate(
        [100.0],
        margin=[
            {
                "MarginPurchaseTodayBalance": 500,
                "MarginPurchaseLimit": 1000,
            }
        ],
    )
    assert sig.action == "HOLD"
    assert "neutral range" in sig.reason
